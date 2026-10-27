# -*- coding: utf-8 -*-
"""hwp_fill.py — 텍스코어 신청서 템플릿 마스터(hwpx)에 블록 JSON을 한글 COM으로 '타이핑'해 넣는 주입 엔진.

왜 COM 타이핑인가
  · 긴 본문을 hwpx XML에 직접 넣으면 줄바꿈 캐시(linesegarray)가 맞지 않아 글자가 겹친다.
    → 한글이 직접 입력(InsertText·BreakPara·TableCreate·InsertPicture)하게 해서 레이아웃을 한글이 계산한다.
  · 짧은 토큰 치환(표지·체크박스·TRL)은 AllReplace(찾아 바꾸기)로 처리한다.

CLI
  python hwp_fill.py --master <template_master.hwpx> --spec <fill_spec.json> --out <out.hwpx>
                     [--hwp out.hwp] [--pdf out.pdf]
  python hwp_fill.py --kill            # 창 없는(자동화가 남긴) Hwp 프로세스만 정리
라이브러리
  from hwp_fill import fill
  report = fill(master, spec_or_path, out, hwp=None, pdf=None)
  # → {"out","hwp","pdf","pages","leftover_tokens","warnings",...}

fill_spec.json 계약은 README_hwp_fill.md 참고(replacements / sections / tables / trl /
delete_english_section / font, 선택: remove_page_breaks, clear_unfilled).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ───────────────────────── 상수 ─────────────────────────
HWPUNIT_PER_MM = 7200 / 25.4          # 283.4646
COL_WIDTH = 48188                      # 양식 본문 폭(A4, 좌우 여백 20mm) = 170.0mm
CELL_MARGIN = 1020                     # 표 셀 좌우 안쪽 여백 합(510×2) — TableCreate ColWidth 는 이 값을 뺀 폭
TOKEN_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")

DEFAULT_FONT = {
    "body_pt": 10, "table_pt": 9, "caption_pt": 8.5,
    "heading_pt": 12, "subheading_pt": 10.5,
    "face": "맑은 고딕", "heading_face": "휴먼명조",
    "line_pct": 160, "table_line_pct": 130,
}
COLORS = {
    "black": (0, 0, 0), "gray": (100, 116, 139), "proves": (30, 58, 138),
    "header_fill": (229, 231, 235), "callout_fill": (241, 245, 249), "callout_line": (148, 163, 184),
}
ALIGN = {"justify": 0, "left": 1, "right": 2, "center": 3}
BULLET_PREFIXES = ("-", "•", "·", "◦", "▪", "※", "→", "①", "②", "③", "④", "⑤", "○", "∎", "■", "□")


def mm(v: float) -> int:
    return int(round(float(v) * HWPUNIT_PER_MM))


def _log(msg):
    print(msg, flush=True)


# ───────────────────────── 프로세스·세션 ─────────────────────────
def kill_orphans(verbose=False) -> int:
    """창이 없는(=자동화가 남긴) Hwp 프로세스만 종료. 사용자가 띄운 한글 창은 건드리지 않는다."""
    if sys.platform != "win32":
        return 0
    ps = ("$p = Get-Process -Name Hwp -ErrorAction SilentlyContinue | "
          "Where-Object { $_.MainWindowHandle -eq 0 }; "
          "if ($p) { $p | Stop-Process -Force; $p.Count } else { 0 }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        n = int(out.splitlines()[-1]) if out else 0
    except Exception:
        n = 0
    if verbose and n:
        _log(f"  고아 한글 프로세스 {n}개 정리")
    return n


def _windowless_hwp() -> int:
    if sys.platform != "win32":
        return 0
    ps = ("@(Get-Process -Name Hwp -ErrorAction SilentlyContinue | "
          "Where-Object { $_.MainWindowHandle -eq 0 }).Count")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        return int(out.splitlines()[-1]) if out else 0
    except Exception:
        return 0


def wait_orphans_gone(timeout=8.0) -> bool:
    """창 없는 Hwp 프로세스가 사라질 때까지 대기(절반이 지나도 남으면 강제 종료).
    직전 세션이 Quit 중인 프로세스에 새 Dispatch 가 붙으면 멈출 수 있어(실측) 세션 사이에 반드시 거친다."""
    t0, killed = time.time(), False
    while time.time() - t0 < timeout:
        if _windowless_hwp() == 0:
            return True
        if not killed and time.time() - t0 > timeout / 2:
            kill_orphans()
            killed = True
        time.sleep(0.3)
    return _windowless_hwp() == 0


class Hwp:
    """한글 COM 세션. with 문을 벗어나면(예외 포함) 문서를 닫고 창 없는 고아 프로세스까지 정리한다.

    watchdog: 숨은 대화상자 등으로 COM 호출이 멈추면 timeout 초 뒤 창 없는 Hwp 를 종료해
    멈춘 호출을 예외로 풀어 준다(기본 600초, 환경변수 TP_HWP_TIMEOUT 으로 조정).
    """

    MSGBOX_MODE = 0x00022011   # 확인→OK, 확인/취소→OK, 예/아니오/취소→아니오, 예/아니오→아니오

    def __init__(self, cleanup=True, visible=False, timeout=None):
        if sys.platform != "win32":
            raise RuntimeError("한글 COM 자동화는 Windows + 한글 설치 환경에서만 동작합니다.")
        self.cleanup = cleanup
        self.visible = visible
        self.timeout = float(timeout or os.environ.get("TP_HWP_TIMEOUT") or 600)
        self.timed_out = False
        self._wd = None
        self.app = None
        self.tmp = None
        self._n = 0

    def _fire(self):
        self.timed_out = True
        _log(f"  ⏱ 한글 COM 응답 없음({self.timeout:.0f}s) — 창 없는 Hwp 강제 종료")
        kill_orphans()

    def __enter__(self, tries=4):
        import threading
        import win32com.client as win32
        wait_orphans_gone()
        self.tmp = Path(tempfile.mkdtemp(prefix="tp_hwp_")).resolve()
        last = None
        for i in range(tries):           # 직전 인스턴스 종료와 경합하면 기동이 실패할 수 있어 재시도
            try:
                self.app = win32.Dispatch("HWPFrame.HwpObject")
                try:
                    self.app.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
                except Exception:
                    pass
                self.app.SetMessageBoxMode(self.MSGBOX_MODE)
                if self.visible:
                    self.app.XHwpWindows.Item(0).Visible = True
                self._wd = threading.Timer(self.timeout, self._fire)
                self._wd.daemon = True
                self._wd.start()
                return self
            except Exception as e:       # 서버 실행 실패 / 작업을 사용할 수 없음
                last = e
                self.app = None
                kill_orphans()
                time.sleep(1.5 * (i + 1))
        raise RuntimeError(f"한글 COM 기동 실패({tries}회 재시도): {last}")

    def __exit__(self, *exc):
        if self._wd:
            self._wd.cancel()
        if self.app is not None and not self.timed_out:
            try:
                self.app.Run("FileClose")
            except Exception:
                pass
            try:
                self.app.Quit()
            except Exception:
                pass
        self.app = None
        if self.cleanup:
            wait_orphans_gone()          # Quit 후 스스로 내려가길 기다리고, 안 내려가면 정리
        if self.tmp:
            shutil.rmtree(self.tmp, ignore_errors=True)
        if self.timed_out and exc and exc[0] is not None:
            raise RuntimeError(f"한글 COM 시간 초과({self.timeout:.0f}s) — 숨은 대화상자 대기로 추정") from exc[1]
        return False

    # ── 파일 ──
    # 한글 COM 파일 입출력은 모두 세션 임시 폴더를 거친다: Dropbox 폴더에 그림이 든 문서를 SaveAs 하거나
    # Dropbox 폴더의 그림을 InsertPicture 하면 한글이 숨은 (보안 확인) 대화상자에서 멈춘다(실측, 검증 ⑦).
    # 임시 폴더에서는 한글·공백이 섞인 경로도 정상 동작한다.
    def _stage(self, name: str) -> Path:
        self._n += 1
        return self.tmp / f"{self._n:03d}_{name}"

    def open(self, path):
        path = Path(path).resolve()      # 한글 COM은 상대경로를 열지 못한다
        if not str(path).startswith(str(self.tmp)):
            src, path = path, self._stage("in" + path.suffix.lower())
            shutil.copy2(src, path)
        if not self.app.Open(str(path), "", "forceopen:true"):
            raise RuntimeError(f"한글이 파일을 열지 못했습니다: {path}")
        return self

    @staticmethod
    def _deliver(tmp_file: Path, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            try:
                if path.exists():
                    os.remove(str(path))
                shutil.copy2(tmp_file, path)
                return path
            except PermissionError:      # 고아 프로세스·동기화 프로그램이 붙잡고 있으면 재시도
                kill_orphans()
                time.sleep(1.0 + i)
        raise RuntimeError(f"결과 파일을 쓸 수 없습니다(잠김): {path}")

    def save_as(self, path, fmt="HWPX"):
        path = Path(path).resolve()
        tmp = self._stage("out" + path.suffix.lower())
        ok = self.app.SaveAs(str(tmp), fmt, "")
        if not tmp.exists():
            raise RuntimeError(f"저장 실패({fmt}): {path} (SaveAs={ok})")
        return self._deliver(tmp, path)

    def save_pdf(self, path):
        path = Path(path).resolve()
        tmp = self._stage("out.pdf")
        act = self.app.CreateAction("FileSaveAsPdf")
        s = act.CreateSet()
        act.GetDefault(s)
        s.SetItem("FileName", str(tmp))
        s.SetItem("Format", "PDF")
        act.Execute(s)
        last = -1
        for _ in range(60):              # PDF 쓰기가 비동기로 끝나는 경우 크기 안정화까지 대기
            if tmp.exists():
                sz = tmp.stat().st_size
                if sz > 0 and sz == last:
                    break
                last = sz
            time.sleep(0.25)
        if not tmp.exists():
            raise RuntimeError(f"PDF 저장 실패: {path}")
        return self._deliver(tmp, path)

    def text(self) -> str:
        return self.app.GetTextFile("TEXT", "") or ""

    def page_count(self) -> int:
        return int(self.app.PageCount)

    # ── 저수준 동작 ──
    def run(self, *names):
        for n in names:
            self.app.Run(n)

    def pos(self):
        return tuple(self.app.GetPos())

    def set_pos(self, lst, para, p=0):
        return self.app.SetPos(lst, para, p)

    def find(self, s: str, from_begin=True) -> bool:
        """찾기 — 찾으면 해당 문자열이 선택된 상태가 된다(표 셀 안도 찾음)."""
        if from_begin:
            self.app.Run("MoveDocBegin")
        ps = self.app.HParameterSet.HFindReplace
        self.app.HAction.GetDefault("RepeatFind", ps.HSet)
        ps.FindString = s
        ps.IgnoreMessage = 1
        ps.FindRegExp = 0
        ps.Direction = self.app.FindDir("Forward")
        return bool(self.app.HAction.Execute("RepeatFind", ps.HSet))

    def all_replace(self, find: str, repl: str):
        self.app.Run("MoveDocBegin")
        act = self.app.CreateAction("AllReplace")
        p = act.CreateSet()
        act.GetDefault(p)
        p.SetItem("FindString", find)
        p.SetItem("ReplaceString", repl)
        p.SetItem("IgnoreMessage", 1)
        p.SetItem("Direction", 2)        # 문서 전체
        act.Execute(p)                   # 반환값은 신뢰할 수 없다 → 본문으로 검증

    def insert(self, s: str):
        if not s:
            return
        p = self.app.HParameterSet.HInsertText
        self.app.HAction.GetDefault("InsertText", p.HSet)
        p.Text = s
        self.app.HAction.Execute("InsertText", p.HSet)

    def char(self, face=None, pt=None, bold=None, italic=None, color=None, ratio=None, spacing=None):
        """글자 모양. 선택이 없으면 '이후 입력'에 적용된다(검증 ②). ratio=장평%, spacing=자간%."""
        cs = self.app.HParameterSet.HCharShape
        self.app.HAction.GetDefault("CharShape", cs.HSet)
        if face:
            for lang in ("Hangul", "Latin", "Hanja", "Japanese", "Other", "Symbol", "User"):
                setattr(cs, "FaceName" + lang, face)
                setattr(cs, "FontType" + lang, 1)   # TTF
        if pt is not None:
            cs.Height = int(round(float(pt) * 100))
        if bold is not None:
            cs.Bold = 1 if bold else 0
        if italic is not None:
            cs.Italic = 1 if italic else 0
        if color is not None:
            cs.TextColor = self.app.RGBColor(*color)
        for lang in ("Hangul", "Latin", "Hanja", "Japanese", "Other", "Symbol", "User"):
            if ratio is not None:
                setattr(cs, "Ratio" + lang, int(ratio))
            if spacing is not None:
                setattr(cs, "Spacing" + lang, int(spacing))
        self.app.HAction.Execute("CharShape", cs.HSet)

    def para(self, align=None, left=None, indent=None, prev=None, nxt=None, line=None, keep_next=False):
        """문단 모양(현재 문단 또는 선택 문단). 여백·간격 단위 HWPUNIT(1pt=100), line=줄간격 %.
        keep_next=True 면 '다음 문단과 함께'(제목·캡션이 쪽 끝에 홀로 남지 않게)."""
        ps = self.app.HParameterSet.HParaShape
        self.app.HAction.GetDefault("ParagraphShape", ps.HSet)
        if align is not None:
            ps.AlignType = ALIGN.get(align, align)
        if left is not None:
            ps.LeftMargin = int(left)
        if indent is not None:
            ps.Indentation = int(indent)
        if prev is not None:
            ps.PrevSpacing = int(prev)
        if nxt is not None:
            ps.NextSpacing = int(nxt)
        if line is not None:
            ps.LineSpacing = int(line)
        ps.KeepWithNext = 1 if keep_next else 0
        self.app.HAction.Execute("ParagraphShape", ps.HSet)

    def table_create(self, rows: int, widths: list[int]):
        """글자처럼 취급하는 표 생성(바깥 여백 0). widths=셀 실제 폭(HWPUNIT). 생성 후 커서는 A1."""
        tc = self.app.HParameterSet.HTableCreation
        self.app.HAction.GetDefault("TableCreate", tc.HSet)
        tc.Rows = rows
        tc.Cols = len(widths)
        tc.WidthType = 2                 # 임의 폭(열 폭 배열 사용)
        tc.HeightType = 0                # 높이 자동
        tc.WidthValue = sum(widths)
        tc.CreateItemArray("ColWidth", len(widths))
        for i, w in enumerate(widths):
            tc.ColWidth.SetItem(i, max(int(w) - CELL_MARGIN, 600))   # ColWidth 는 안쪽 여백 제외 폭
        tc.TableProperties.TreatAsChar = 1
        tc.TableProperties.Width = sum(widths)
        for k in ("OutsideMarginLeft", "OutsideMarginRight", "OutsideMarginTop", "OutsideMarginBottom"):
            setattr(tc.TableProperties, k, 0)
        ok = self.app.HAction.Execute("TableCreate", tc.HSet)
        if not ok:
            raise RuntimeError("TableCreate 실패")

    def cell_style(self, fill=None, border=None, border_color=(0, 0, 0), border_width="0.12mm"):
        """현재 셀(또는 셀 블록)의 배경·테두리. border: None=유지, 'none'=없음, 'solid'=실선."""
        cb = self.app.HParameterSet.HCellBorderFill
        self.app.HAction.GetDefault("CellBorderFill", cb.HSet)
        if fill is not None:
            cb.FillAttr.type = self.app.BrushType("NullBrush|WinBrush")
            cb.FillAttr.WinBrushFaceColor = self.app.RGBColor(*fill)
            cb.FillAttr.WinBrushHatchColor = self.app.RGBColor(0, 0, 0)
            cb.FillAttr.WinBrushFaceStyle = self.app.HatchStyle("None")
            cb.FillAttr.WindowsBrush = 1
        if border is not None:
            lt = 0 if border == "none" else self.app.HwpLineType("Solid")
            for side in ("Left", "Right", "Top", "Bottom"):
                cb.HSet.SetItem("BorderType" + side, lt)
                cb.HSet.SetItem("BorderWidth" + side, self.app.HwpLineWidth(border_width))
                cb.HSet.SetItem("BorderColor" + side, self.app.RGBColor(*border_color))
            # 셀 블록의 안쪽 가로·세로 선(이 항목이 없으면 바깥선만 바뀐다 — 검증 ⑥)
            for k in ("TypeHorz", "TypeVert"):
                cb.HSet.SetItem(k, lt)
            for k in ("WidthHorz", "WidthVert"):
                cb.HSet.SetItem(k, self.app.HwpLineWidth(border_width))
            for k in ("ColorHorz", "ColorVert", "CorlorHorz", "CorlorVert"):
                cb.HSet.SetItem(k, self.app.RGBColor(*border_color))
        self.app.HAction.Execute("CellBorderFill", cb.HSet)

    def goto_cell(self, r: int, c: int):
        """현재 표 안에서 (r, c) 셀로 이동(병합 없는 격자 기준)."""
        self.run("TableColBegin", "TableColPageUp")
        for _ in range(r):
            self.app.Run("TableLowerCell")
        for _ in range(c):
            self.app.Run("TableRightCell")

    def select_all_cells(self):
        self.run("TableColBegin", "TableColPageUp", "TableCellBlock", "TableCellBlockExtend",
                 "TableColPageDown", "TableColEnd")

    def exit_table(self):
        """표 밖으로: CloseEx 는 표가 든 문단의 맨 앞(표 앞)으로 가므로 문단 끝으로 다시 이동(검증 ④)."""
        self.run("Cancel", "CloseEx", "MoveParaEnd")

    def picture(self, path, w_mm, h_mm):
        """그림 삽입(문서에 포함, 지정 크기 mm, 글자처럼 취급) — 검증 ⑤."""
        ctrl = self.app.InsertPicture(str(Path(path).resolve()), True, 1, False, False, 0,
                                      float(w_mm), float(h_mm))
        if ctrl is None:
            raise RuntimeError(f"InsertPicture 실패: {path}")
        try:
            props = ctrl.Properties
            if not props.Item("TreatAsChar"):
                props.SetItem("TreatAsChar", True)
                ctrl.Properties = props
        except Exception:
            pass
        return ctrl


# ───────────────────────── 마스터 XML 분석(고정 표 구조) ─────────────────────────
def master_tables(master) -> dict:
    """마스터 hwpx 에서 고정 표 토큰별 구조를 읽는다: rows, cols, anchor(r,c), 첫 열 라벨, 표 위 제목."""
    from lxml import etree
    ns = {"hp": "http://www.hancom.co.kr/hwpml/2011/paragraph"}
    hp = "{%s}" % ns["hp"]
    with zipfile.ZipFile(master) as zf:
        root = etree.fromstring(zf.read("Contents/section0.xml"))

    def txt(el):
        return "".join(t.xpath("string()") for t in el.iter(hp + "t"))

    def own(p):
        return "".join(t.xpath("string()") for t in p.findall("hp:run/hp:t", ns))

    out = {}
    tops = root.findall("hp:p", ns)
    for pi, p in enumerate(tops):
        for tbl in p.iter(hp + "tbl"):
            cells, widths = {}, {}
            for tc in tbl.findall("hp:tr/hp:tc", ns):
                a = tc.find("hp:cellAddr", ns)
                cells[(int(a.get("rowAddr")), int(a.get("colAddr")))] = txt(tc)
                widths[(int(a.get("rowAddr")), int(a.get("colAddr")))] = int(tc.find("hp:cellSz", ns).get("width"))
            for (r, c), t in cells.items():
                m = re.fullmatch(r"\s*\{\{(T_[A-Z]+)\}\}\s*", t)
                if not m:
                    continue
                rows, cols = int(tbl.get("rowCnt")), int(tbl.get("colCnt"))
                title = own(tops[pi - 1]).strip() if pi > 0 else ""
                out[m.group(1)] = {
                    "rows": rows, "cols": cols, "anchor": (r, c),
                    "labels": [cells.get((rr, 0), "").strip() for rr in range(rows)],
                    "col_widths": [widths.get((r, cc), 0) for cc in range(cols)],
                    "title": title if title.startswith("□") else "",
                }
    return out


def _prep_copy(master: Path, dst: Path, remove_page_breaks=False):
    """마스터를 작업 사본으로 복사(마스터는 수정하지 않음). 필요 시 장 시작 강제 쪽 나눔 해제(XML 속성만)."""
    if not remove_page_breaks:
        shutil.copy2(master, dst)
        return
    with zipfile.ZipFile(master) as zf:
        names = zf.namelist()
        blobs = {n: zf.read(n) for n in names}
    xml = blobs["Contents/section0.xml"].decode("utf-8")
    xml = re.sub(r'(<hp:p\b[^>]*?)pageBreak="1"', r'\1pageBreak="0"', xml)
    blobs["Contents/section0.xml"] = xml.encode("utf-8")
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in (["mimetype"] if "mimetype" in blobs else []) + [n for n in names if n != "mimetype"]:
            if n == "mimetype":
                zi = zipfile.ZipInfo("mimetype")
                zi.compress_type = zipfile.ZIP_STORED
                zf.writestr(zi, blobs[n])
            else:
                zf.writestr(n, blobs[n])


# ───────────────────────── 보조 ─────────────────────────
def _vis_len(s: str) -> int:
    """대략적 표시 폭(한글·전각 2, 그 외 1)."""
    return sum(2 if ord(ch) >= 0x1100 else 1 for ch in str(s))


def _overflows(text: str, pt: float, cell_w: int) -> bool:
    """칸 폭(HWPUNIT) 대비 글자 폭 추정이 넘치면 True → 장평 88%·자간 -6% 로 줄여 줄바꿈을 줄인다."""
    if not cell_w:
        return False
    em = float(pt) * 25.4 / 72                       # 1em(mm)
    est = sum(em if ord(ch) >= 0x1100 else em * 0.55 for ch in text)
    return est > (cell_w - CELL_MARGIN) / HWPUNIT_PER_MM


def _img_size(path: Path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        data = path.read_bytes()[:32]
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", data[16:24])
    return None


def _auto_widths(columns, rows, total=COL_WIDTH, min_mm=12.0):
    n = len(columns)
    raw = []
    for j in range(n):
        lens = [_vis_len(columns[j])] + [_vis_len(r[j]) for r in rows if j < len(r)]
        raw.append(min(max(lens), 56) + 6)
    s = sum(raw)
    w = [total * x / s for x in raw]
    lo = mm(min_mm)
    for _ in range(3):                    # 최소 폭 보장 후 나머지 비례 재배분
        short = [i for i, x in enumerate(w) if x < lo]
        if not short:
            break
        need = sum(lo - w[i] for i in short)
        rich = [i for i in range(n) if i not in short]
        rs = sum(w[i] for i in rich) or 1
        for i in short:
            w[i] = lo
        for i in rich:
            w[i] -= need * w[i] / rs
    w = [int(x) for x in w]
    w[-1] += total - sum(w)
    return w


def _scaled_widths(mm_list, total=COL_WIDTH):
    s = float(sum(mm_list))
    w = [int(total * x / s) for x in mm_list]
    w[-1] += total - sum(w)
    return w


# ───────────────────────── 채움 본체 ─────────────────────────
class Filler:
    def __init__(self, h: Hwp, spec: dict, report: dict, base_dir: Path, tmp_dir: Path):
        self.h = h
        self.spec = spec
        self.r = report
        self.base = base_dir
        self.tmp = tmp_dir
        self.f = dict(DEFAULT_FONT, **(spec.get("font") or {}))
        self._img_n = 0
        self.deferred = {}               # 자리표시 토큰 → 실제 문자열(메일·URL 자동 하이퍼링크 회피)

    def _stage_image(self, p: Path) -> Path:
        """그림을 임시 폴더(ASCII 이름)로 복사 — Dropbox 폴더의 그림을 InsertPicture 하면
        한글이 숨은 대화상자에서 멈춘다(실측, 검증 ⑦). 임시 폴더 사본은 즉시 삽입된다."""
        self._img_n += 1
        dst = self.tmp / f"img_{self._img_n:03d}{p.suffix.lower()}"
        shutil.copy2(p, dst)
        return dst

    def warn(self, msg):
        self.r["warnings"].append(msg)
        _log("  ⚠ " + msg)

    # ── 글자·문단 프리셋 ──
    def _body_char(self, pt=None, bold=False, color="black", face=None, condense=False):
        self.h.char(face=face or self.f["face"], pt=pt or self.f["body_pt"], bold=bold, italic=False,
                    color=COLORS.get(color, color) if isinstance(color, str) else color,
                    ratio=88 if condense else 100, spacing=-6 if condense else 0)

    def _safe(self, part: str) -> str:
        """메일·URL 을 InsertText 로 치면 한글이 자동 하이퍼링크(파란 밑줄)로 바꾸고, 표 칸의
        'YYYY.MM.DD' 날짜는 끝에 '.'을 덧붙인다(입력 자동 서식, 실측). 이런 조각은 자리표시 토큰을
        대신 입력하고 마지막에 AllReplace 로 바꾸면 입력한 그대로 남는다."""
        if re.search(r"@|://|www\.|\d{2,4}[./-]\d{1,2}[./-]\d{1,2}", part):
            key = "{{_L%03d}}" % (len(self.deferred) + 1)
            self.deferred[key] = part
            return key
        return part

    def _rich(self, text, pt=None, bold=False, color="black", condense=False):
        """'**굵게**' 표기를 지원하는 입력."""
        parts = str(text).split("**")
        for i, part in enumerate(parts):
            if not part:
                continue
            self._body_char(pt=pt, bold=bold or (i % 2 == 1), color=color, condense=condense)
            self.h.insert(self._safe(part))

    def flush_deferred(self):
        for k, v in self.deferred.items():
            self.h.all_replace(k, v)

    # ── 블록 ──
    def blocks(self, blocks: list):
        first = True
        for b in blocks:
            t = (b.get("type") or "").lower()
            fn = getattr(self, "b_" + t, None)
            if fn is None:
                self.warn(f"알 수 없는 블록 type '{t}' — 건너뜀")
                continue
            if not first:
                self.h.run("BreakPara")
            fn(b, first)
            first = False

    def b_heading(self, b, first):
        self.h.para(align="left", left=0, indent=0, prev=0 if first else 700, nxt=150, line=self.f["line_pct"],
                    keep_next=True)
        self.h.char(face=self.f["heading_face"], pt=self.f["heading_pt"], bold=True, italic=False,
                    color=COLORS["black"])
        self.h.insert(b.get("text", ""))

    def b_subheading(self, b, first):
        self.h.para(align="left", left=0, indent=0, prev=0 if first else 350, nxt=80, line=self.f["line_pct"],
                    keep_next=True)
        self._body_char(pt=self.f["subheading_pt"], bold=True)
        self.h.insert(b.get("text", ""))

    def b_para(self, b, first):
        text = str(b.get("text", ""))
        lines = text.split("\n")
        ascii_ratio = sum(ch.isascii() for ch in text) / max(len(text), 1)
        align = b.get("align") or ("left" if ascii_ratio > 0.85 else "justify")   # 영문은 양쪽 정렬 시 단어 간격이 벌어짐
        for i, ln in enumerate(lines):
            if i:
                self.h.run("BreakPara")
            self.h.para(align=align, left=0, indent=0, prev=0, nxt=60, line=self.f["line_pct"])
            self._rich(ln, bold=bool(b.get("bold")))

    def b_bullets(self, b, first):
        items = b.get("items") or []
        for i, it in enumerate(items):
            if i:
                self.h.run("BreakPara")
            level = 1
            if isinstance(it, dict):
                level = int(it.get("level", 1))
                it = it.get("text", "")
            it = str(it)
            mark = "- " if level == 1 else "· "
            if it.lstrip().startswith(BULLET_PREFIXES):
                mark = ""
            left = 1300 if level == 1 else 2500           # 내어쓰기: 줄바꿈된 줄이 표식 뒤에 맞도록
            self.h.para(align="justify", left=left, indent=-700, prev=0, nxt=40, line=self.f["line_pct"])
            self._rich(mark + it)

    def b_spacer(self, b, first):
        self.h.para(align="left", left=0, indent=0, prev=0, nxt=0, line=100)
        self._body_char(pt=b.get("pt", 6))

    def _caption(self, text, bold=True, color="black", align="center", prev=200, nxt=60, pt=None, keep_next=False):
        self.h.para(align=align, left=0, indent=0, prev=prev, nxt=nxt, line=130, keep_next=keep_next)
        self._rich(text, pt=pt or self.f["caption_pt"], bold=bold, color=color)

    def b_table(self, b, first):
        cols = [str(c) for c in (b.get("columns") or [])]
        rows = [[("" if v is None else str(v)) for v in r] for r in (b.get("rows") or [])]
        if not cols and rows:
            cols, rows = rows[0], rows[1:]
        n = len(cols)
        if n == 0:
            self.warn("table 블록에 columns/rows 없음 — 건너뜀")
            return
        rows = [(r + [""] * n)[:n] if len(r) <= n else r[:n - 1] + [" / ".join(r[n - 1:])] for r in rows]
        pt = b.get("font_pt") or self.f["table_pt"]
        if b.get("caption"):
            self._caption(b["caption"], prev=0 if first else 200, keep_next=True)
            self.h.run("BreakPara")
        widths = _scaled_widths(b["col_widths_mm"]) if b.get("col_widths_mm") and len(b["col_widths_mm"]) == n \
            else _auto_widths(cols, rows)
        center_col = [max([_vis_len(r[j]) for r in rows] or [0]) <= 14 for j in range(n)]
        self.h.para(align="center", left=0, indent=0, prev=0, nxt=0, line=100)
        self.h.table_create(1 + len(rows), widths)
        grid = [cols] + rows
        for ri, row in enumerate(grid):
            for ci, val in enumerate(row):
                if ri or ci:
                    self.h.run("TableRightCell")
                head = ri == 0
                self.h.para(align="center" if head or center_col[ci] else "left", left=0, indent=0,
                            prev=0, nxt=0, line=self.f["table_line_pct"])
                for k, ln in enumerate(val.split("\n")):
                    if k:
                        self.h.run("BreakPara")
                    self._rich(ln, pt=pt, bold=head)
                if head:
                    self.h.cell_style(fill=COLORS["header_fill"])
        self.h.exit_table()
        if b.get("source"):
            self.h.run("BreakPara")
            self._caption(b["source"], bold=False, color="gray", align="left", prev=40, nxt=60,
                          pt=float(self.f["caption_pt"]) - 0.5)

    def b_figure(self, b, first):
        imgs = b.get("images") or []
        if isinstance(imgs, (str, dict)):
            imgs = [imgs]
        imgs = [{"path": i} if isinstance(i, str) else dict(i) for i in imgs]
        if not imgs:
            self.warn("figure 블록에 images 없음 — 건너뜀")
            return
        n = len(imgs)
        widths = _scaled_widths([1] * n)
        cell_mm = (widths[0] - CELL_MARGIN) / HWPUNIT_PER_MM
        has_cap = any(b.get(k) for k in ("caption", "proves", "source"))
        self.h.para(align="center", left=0, indent=0, prev=0 if first else 120, nxt=0, line=100)
        self.h.table_create(2 if has_cap else 1, widths)
        for i, im in enumerate(imgs):
            if i:
                self.h.run("TableRightCell")
            self.h.para(align="center", left=0, indent=0, prev=0, nxt=0, line=100)
            p = Path(im.get("path", ""))
            if not p.is_absolute():
                p = (self.base / p).resolve()
            size = _img_size(p) if p.exists() else None
            if not size:
                self.warn(f"그림 파일 없음/판독 불가: {p}")
                self._rich(f"[그림 없음: {p.name}]", pt=self.f["caption_pt"], color="gray")
                continue
            w = min(float(im.get("width_mm") or cell_mm * 0.96), cell_mm * 0.98)
            h = w * size[1] / size[0]
            max_h = float(im.get("max_height_mm") or b.get("max_height_mm") or 110)
            if h > max_h:
                h, w = max_h, max_h * size[0] / size[1]
            self.h.picture(self._stage_image(p), round(w, 1), round(h, 1))
            self.r["images"] += 1
            if im.get("label"):
                self.h.run("BreakPara")
                self.h.para(align="center", left=0, indent=0, prev=40, nxt=0, line=120)
                self._rich(im["label"], pt=self.f["caption_pt"], color="gray")
        if has_cap:
            self.h.run("TableRightCell")
            if n > 1:
                self.h.run("TableCellBlock", "TableCellBlockExtend", "TableColEnd", "TableMergeCell", "Cancel")
            parts = []
            if b.get("caption"):
                parts.append(("caption", b["caption"]))
            if b.get("proves"):
                parts.append(("proves", b["proves"]))
            if b.get("source"):
                parts.append(("source", b["source"]))
            for k, (kind, val) in enumerate(parts):
                if k:
                    self.h.run("BreakPara")
                if kind == "caption":
                    self._caption(val, prev=60, nxt=0)
                elif kind == "proves":
                    self._caption(val, bold=True, color="proves", prev=20, nxt=0)
                else:
                    self._caption(val, bold=False, color="gray", prev=20, nxt=0,
                                  pt=float(self.f["caption_pt"]) - 0.5)
        self.h.select_all_cells()
        self.h.cell_style(border="none")
        self.h.exit_table()

    def b_callout(self, b, first):
        self.h.para(align="center", left=0, indent=0, prev=0 if first else 120, nxt=0, line=100)
        self.h.table_create(1, [COL_WIDTH])
        self.h.para(align=b.get("align", "left"), left=0, indent=0, prev=60, nxt=60, line=self.f["line_pct"])
        lines = str(b.get("text", "")).split("\n")
        for i, ln in enumerate(lines):
            if i:
                self.h.run("BreakPara")
            self._rich(ln, pt=b.get("font_pt") or self.f["body_pt"], bold=True)
        self.h.cell_style(fill=COLORS["callout_fill"], border="solid", border_color=COLORS["callout_line"])
        self.h.exit_table()

    # ── 섹션 ──
    def section(self, key, blocks):
        tok = "{{%s}}" % key
        if not self.h.find(tok):
            self.warn(f"섹션 앵커 {tok} 없음(마스터 확인 또는 영문 섹션 삭제됨)")
            return False
        self.h.run("Delete")
        if not blocks:
            self.warn(f"빈 섹션: {key}")
            return False
        self.blocks(blocks)
        self.r["sections_filled"].append(key)
        return True

    # ── 고정 표 ──
    def fixed_table(self, key, cfg, info):
        tok = "{{%s}}" % key
        if not self.h.find(tok):
            self.warn(f"고정 표 앵커 {tok} 없음")
            return
        self.h.run("Delete")
        rows = [[("" if v is None else str(v)) for v in r] for r in (cfg.get("rows") or [])]
        rows = [r for r in rows if any(x.strip() for x in r)]
        keep_first = bool(cfg.get("keep_first_col", info["anchor"][1] == 1))
        ar, ac = info["anchor"]
        ncols, nrows = info["cols"], info["rows"]
        pt = cfg.get("font_pt") or self.f["table_pt"]

        if not rows:
            if cfg.get("delete_if_empty"):
                self._delete_fixed_table(info, cfg.get("empty_text"))
            else:
                self.h.run("Cancel")
            self.r["tables"][key] = 0
            return

        # 데이터 행 → 표 행 배정
        labels = info["labels"]                         # 표 전체 행의 첫 열 라벨
        data_rows = list(range(ar, nrows))              # 채울 수 있는 표 행 번호
        assign = []                                     # (표 행, 값 목록, 새 라벨 or None)
        if keep_first:
            used = set()
            for r in rows:
                lab, vals = r[0].strip(), r[1:]
                slot = next((tr for tr in data_rows if tr not in used and labels[tr].strip() == lab), None)
                if slot is None:
                    assign.append((None, vals, lab))
                else:
                    used.add(slot)
                    assign.append((slot, vals, None))
            unused = [tr for tr in data_rows if tr not in used]
        else:
            for i, r in enumerate(rows):
                assign.append((data_rows[i] if i < len(data_rows) else None, r, None))
            unused = data_rows[len(rows):]

        width = ncols - ac
        cur_rows = nrows
        for slot, vals, newlab in assign:
            if slot is None:                            # 행 추가(마지막 행 아래)
                self.h.goto_cell(cur_rows - 1, 0)
                self.h.run("TableAppendRow")
                slot = cur_rows
                cur_rows += 1
                if newlab is not None:
                    self.h.goto_cell(slot, 0)
                    self.h.para(align="center")
                    self._rich(newlab, pt=pt)
            if len(vals) > width:
                self.warn(f"{key}: 값 {len(vals)}개 > 칸 {width}개 — 넘친 값은 마지막 칸에 합침")
                vals = vals[:width - 1] + [" / ".join(vals[width - 1:])]
            for j, v in enumerate(vals):
                if not v:
                    continue
                self.h.goto_cell(slot, ac + j)
                cw = (info.get("col_widths") or [0] * ncols)[ac + j]
                for k, ln in enumerate(v.split("\n")):
                    if k:
                        self.h.run("BreakPara")
                    self._rich(ln, pt=pt, condense=_overflows(ln, pt, cw))

        # 남는 행 정리: 첫 열 라벨 표는 EM 행만 삭제(EL/PM/PI 는 유지), 일반 표는 trim_empty_rows(기본 켬)
        to_delete = []
        for tr in unused:
            lab = labels[tr].strip()
            if keep_first:
                if lab.upper().startswith("EM"):
                    to_delete.append(tr)
                else:
                    self.warn(f"{key}: '{lab}' 행 데이터 없음(빈 칸 유지)")
            elif cfg.get("trim_empty_rows", True):
                to_delete.append(tr)
        for tr in sorted(to_delete, reverse=True):
            self.h.goto_cell(tr, 0)
            self.h.run("TableDeleteRow")
        self.h.run("Cancel")
        self.r["tables"][key] = len(assign)

    def _delete_fixed_table(self, info, empty_text=None):
        """표 전체 삭제(+ 표 바로 위 '□' 제목 문단). empty_text 가 있으면 제목은 두고 표 자리에 그 문장."""
        tbl = self.h.app.ParentCtrl
        self.h.run("Cancel", "CloseEx")
        lst, para, _ = self.h.pos()
        self.h.app.DeleteCtrl(tbl)
        if empty_text:
            self.h.set_pos(lst, para, 0)
            self.h.para(align="left", left=0, indent=0, prev=0, nxt=60, line=self.f["line_pct"])
            self._rich(empty_text)
            return
        title = info.get("title") or ""
        if title and self.h.find(title.strip()) and self.h.pos()[1] == para - 1:
            self.h.set_pos(lst, para - 1, 0)
            self.h.run("MoveSelNextParaBegin", "MoveSelNextParaBegin", "Delete")
        else:
            self.h.set_pos(lst, para, 0)
            self.h.run("MoveSelNextParaBegin", "Delete")

    # ── 영문 섹션 삭제 ──
    def delete_english(self):
        if not self.h.find("Summary of Business Start-up Item"):
            self.warn("영문 요약 제목을 찾지 못해 삭제하지 못함")
            return
        self.h.run("Cancel", "CloseEx")              # 제목 상자(표) 앞, 그 문단 맨 앞
        lst, para, _ = self.h.pos()
        self.h.set_pos(lst, para, 0)
        self.h.run("MoveSelDocEnd", "Delete")
        if para > 0:
            self.h.run("DeleteBack")                     # 남은 빈 문단을 앞 문단에 붙임


# ───────────────────────── 진입점 ─────────────────────────
def _load_spec(spec):
    if isinstance(spec, (str, Path)):
        p = Path(spec)
        return json.loads(p.read_text(encoding="utf-8")), p.resolve().parent
    return dict(spec), Path.cwd()


def fill(master, spec, out, hwp=None, pdf=None, verbose=True) -> dict:
    """마스터 + 채움 사양 → out.hwpx (+hwp, +pdf). 반환: 리포트 dict."""
    t0 = time.time()
    spec, base = _load_spec(spec)
    master, out = Path(master).resolve(), Path(out).resolve()
    if not master.exists():
        raise FileNotFoundError(master)
    report = {"out": str(out), "hwp": None, "pdf": None, "pages": None, "leftover_tokens": [],
              "warnings": [], "sections_filled": [], "tables": {}, "images": 0}
    infos = master_tables(master)
    del_en = bool(spec.get("delete_english_section"))

    with tempfile.TemporaryDirectory(prefix="tp_fill_") as td:
        work = Path(td) / "work.hwpx"
        _prep_copy(master, work, bool(spec.get("remove_page_breaks")))
        with Hwp() as h:
            h.open(work)
            fl = Filler(h, spec, report, base, Path(td))
            # 1) 짧은 치환(표지 토큰·체크박스)
            for k, v in (spec.get("replacements") or {}).items():
                h.all_replace(str(k), "" if v is None else str(v))
            # 2) TRL
            lvl = (spec.get("trl") or {}).get("level")
            for n in range(1, 10):
                h.all_replace("{{TRL_%d}}" % n, "( √ )" if lvl is not None and int(lvl) == n else "(    )")
            # 3) 고정 표
            for key, cfg in (spec.get("tables") or {}).items():
                if key not in infos:
                    fl.warn(f"고정 표 {key} 가 마스터에 없음")
                    continue
                if verbose:
                    _log(f"  표 {key}")
                fl.fixed_table(key, cfg or {}, infos[key])
            # 4) 본문 섹션
            secs = spec.get("sections") or {}
            for key, blocks in secs.items():
                if del_en and key.startswith("S_EN"):
                    continue
                if verbose:
                    _log(f"  섹션 {key} ({len(blocks or [])} 블록)")
                fl.section(key, blocks or [])
            # 5) 영문 섹션 삭제
            if del_en:
                fl.delete_english()
            # 5-1) spec 에 없는 섹션 앵커는 비우고 경고(남은 토큰 BLOCKING 대상에서 제외 — QA 가 빈 섹션으로 잡는다)
            for key in sorted(set(re.findall(r"\{\{(S_[A-Z0-9_]+)\}\}", h.text()))):
                if h.find("{{%s}}" % key):
                    h.run("Delete")
                    fl.warn(f"빈 섹션: {key} — sections 에 없어 앵커만 비움")
            fl.flush_deferred()
            # 6) 남은 토큰
            body = h.text()
            left = sorted(set(TOKEN_RE.findall(body)))
            if left and spec.get("clear_unfilled"):
                for tkn in left:
                    h.all_replace(tkn, "")
                fl.warn(f"채우지 않은 토큰 {len(left)}개를 빈칸 처리: {', '.join(left)}")
                left = sorted(set(TOKEN_RE.findall(h.text())))
            report["leftover_tokens"] = left
            if left:
                fl.warn(f"남은 토큰 {len(left)}개: {', '.join(left)}")
            # 7) 저장
            h.save_as(out, "HWPX")
            report["pages"] = h.page_count()
            if hwp:
                report["hwp"] = str(h.save_as(hwp, "HWP"))
            if pdf:
                report["pdf"] = str(h.save_pdf(pdf))
    report["seconds"] = round(time.time() - t0, 1)
    if verbose:
        _log(f"✅ {out.name}: {report['pages']}쪽, 그림 {report['images']}개, "
             f"남은 토큰 {len(report['leftover_tokens'])}개, 경고 {len(report['warnings'])}건 ({report['seconds']}s)")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="텍스코어 신청서 hwp 주입 엔진(한글 COM)")
    ap.add_argument("--master")
    ap.add_argument("--spec")
    ap.add_argument("--out")
    ap.add_argument("--hwp")
    ap.add_argument("--pdf")
    ap.add_argument("--report", help="리포트 JSON 저장 경로")
    ap.add_argument("--kill", action="store_true", help="창 없는 Hwp 프로세스만 정리하고 종료")
    a = ap.parse_args(argv)
    if a.kill:
        _log(f"정리: {kill_orphans()}개")
        return 0
    if not (a.master and a.spec and a.out):
        ap.error("--master, --spec, --out 이 필요합니다")
    rep = fill(a.master, a.spec, a.out, hwp=a.hwp, pdf=a.pdf)
    if a.report:
        Path(a.report).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 1 if rep["leftover_tokens"] else 0


if __name__ == "__main__":
    sys.exit(main())
