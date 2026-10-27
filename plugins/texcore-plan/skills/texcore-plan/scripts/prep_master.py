# -*- coding: utf-8 -*-
"""prep_master.py — 원본 신청서 양식(hwp) → 앵커 토큰을 박은 템플릿 마스터(hwpx) 1회 제작.

절차(재현 가능)
  1) 원본 hwp를 임시 폴더에 복사 → 한글 COM으로 hwpx 저장(원본은 손대지 않음)
  2) Contents/section0.xml 을 lxml로 편집
       - 작성요령 박스(표)·표지 '<작성 시 주의 사항>' 박스·'※ 탐색팀의 국문명은…(제출 시 삭제)' 안내문 삭제
       - 표지 값 칸·본문 앵커·고정 표 첫 데이터 셀·TRL 칸에 {{토큰}} 삽입
       - 표 안 예시 텍스트('<예> …', '-') 삭제, Ⅰ-2의 □ 소제목 4개 제거(heading 블록으로 다시 씀)
       - 편집한 문단은 linesegarray(줄바꿈 캐시)를 지워 한글이 다시 계산하게 함
  3) 재패키징(mimetype 첫 항목·무압축) → 한글 COM으로 열어 다시 SaveAs(정규화)
  4) 토큰 전수·작성요령 잔존 검사 → template_master.hwpx + anchors.json + 미리보기 PDF/PNG

사용
  python prep_master.py                       # 기본 경로(스크립트 폴더 기준 ../assets/template)
  python prep_master.py --src <원본.hwp> --out-dir <폴더> --preview <미리보기 폴더>
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hwp_fill as hf  # noqa: E402  (Hwp 세션·고아 프로세스 정리 공용)

DEF_SRC = HERE.parent / "assets" / "template" / "사업신청서_원본양식_2026.hwp"
DEF_OUT = HERE.parent / "assets" / "template"
DEF_PREVIEW = HERE.parent.parent / "tests" / "master_preview"

NS = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
}
HP = "{%s}" % NS["hp"]
SECTION = "Contents/section0.xml"
HEADER = "Contents/header.xml"

BODY_CHARPR = "9"      # 맑은 고딕 10pt 보통 검정 — 토큰·여백 문단용
BODY_PARAPR = "3"      # 양식 본문 기본 문단(양쪽 정렬, 160%)

# (제목 접두어, 토큰, 모드, 설명)
#   모드 'empty'           : 바로 뒤 빈 문단들을 [토큰 문단 + 여백 문단 1개]로 정리
#   모드 'until:<접두어>'  : 그 제목 전까지(□ 소제목 포함) 모두 지우고 [토큰 + 여백]
SECTION_ANCHORS = [
    ("1. 실험실창업 탐색의 추진 동기와 목표", "S_I1", "empty", "Ⅰ-1 실험실창업 탐색의 추진 동기와 목표 본문"),
    ("2. 실험실 창업(탐색) 아이템", "S_I2", "until:Ⅱ. 핵심기술",
     "Ⅰ-2 아이템 본문(양식의 □ 소제목 4개는 마스터에서 제거 — heading 블록으로 다시 쓴다)"),
    ("1. 핵심기술의 개요", "S_II1", "empty", "Ⅱ-1 핵심기술의 개요(세 문장 공식)"),
    ("□ 핵심기술 확보계획", "S_II2_PLAN", "empty", "Ⅱ-2-2 '□ 핵심기술 확보계획' 아래"),
    ("□ 핵심기술 up-grade 계획", "S_II2_UPGRADE", "empty", "Ⅱ-2-2 '□ 핵심기술 up-grade 계획' 아래"),
    ("1. 창업(탐색) 아이템의 시작품(시제품) 제작계획", "S_III1", "empty", "Ⅲ-1 시작품(시제품) 제작계획"),
    ("2. 사업화 추진계획", "S_III2", "empty", "Ⅲ-2 사업화 추진계획(추진일정 도표)"),
    ("3. 창업 추진 애로사항 및 건의사항", "S_III3", "empty", "Ⅲ-3 애로사항·건의사항(선택)"),
    ("1) What is the core technology", "S_EN1", "empty", "Summary 영문 질문 1) 아래"),
    ("2) What is the main problem", "S_EN2", "empty", "Summary 영문 질문 2) 아래"),
    ("3) What makes your solutions", "S_EN3", "empty", "Summary 영문 질문 3) 아래(문서 끝)"),
]
# 이 제목 바로 뒤의 빈 문단은 지운다(작성요령 박스가 빠진 자리 정리)
TIGHTEN_AFTER = ["2-1. 핵심기술의 지식재산권 현황", "2-2. 핵심기술 확보계획"]
# 강제 쪽 나눔을 푸는 문단(양식 배치용 쪽 나눔 — 채운 뒤에는 빈 쪽을 만든다)
UNBREAK = ["□ 핵심기술의 권리인 및 발명자와의 관계"]

ROLE_FIELDS = [  # (행 오프셋, 열, 접미사, 설명)
    (0, 2, "NAME", "성명('(서명)' 앞)"), (0, 6, "BIRTH", "생년월일"),
    (1, 2, "ORG", "소속기관/학과(부서)"), (1, 6, "MAJOR", "전공분야"),
    (2, 2, "DEGREE", "최종학위(EL은 최종학위/현재학적)"), (2, 6, "TEL", "Tel"),
    (3, 2, "PHONE", "핸드폰"), (3, 6, "EMAIL", "E-mail"),
]
ROLE_ROWS = {"EL": 12, "PM": 16, "PI": 20}

KEEP_WITH_NEXT = [   # 마스터에서 '다음 문단과 함께'를 켜는 양식 제목(찾기 문자열)
    "Ⅰ. 실험실 창업(탐색) 아이템", "1. 실험실창업 탐색의 추진 동기와 목표", "2. 실험실 창업(탐색) 아이템",
    "Ⅲ. 사업화 추진계획", "Ⅳ. 실험실창업탐색팀",
    "Ⅱ. 핵심기술", "1. 핵심기술의 개요", "2. 핵심기술의 확보계획", "2-1. 핵심기술의 지식재산권 현황",
    "□ 특허 출원/등록 실적", "□ 기타 지식재산권", "□ 핵심기술의 권리인 및 발명자와의 관계",
    "2-2. 핵심기술 확보계획", "□ 핵심기술 확보계획", "□ 핵심기술의 개발 단계", "□ 핵심기술 up-grade 계획",
    "1. 창업(탐색) 아이템의 시작품(시제품) 제작계획", "2. 사업화 추진계획", "3. 창업 추진 애로사항 및 건의사항",
    "1. 실험실창업탐색팀의 구성", "2. 구성원의 주요 경력 및 역할",
    "1) What is the core technology", "2) What is the main problem", "3) What makes your solutions",
]

CHECKBOXES = ["□수도권", "□충청권", "□대경권", "□호남권", "□동남권", "□여성특화형", "□출연(연)특화형",
              "□ 신청 실험실창업혁신단 파악 불가", "□ 해외교육형", "□ 국내교육형", "□ 여성특화형", "□ 출연(연)특화형"]


# ───────────────────────── XML 유틸 ─────────────────────────
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def own_text(p) -> str:
    """문단 자신의 텍스트(중첩 표 안 텍스트 제외)."""
    return "".join(t.xpath("string()") for t in p.findall("hp:run/hp:t", NS))


def all_text(el) -> str:
    return "".join(t.xpath("string()") for t in el.iter(HP + "t"))


def has_object(p) -> bool:
    """문단에 표·그림·구역정의 등 텍스트 외 개체가 있는지."""
    for run in p.findall("hp:run", NS):
        for ch in run:
            if ch.tag != HP + "t":
                return True
    return False


def is_empty_para(p) -> bool:
    return not own_text(p).strip() and not has_object(p)


def drop_lineseg(p):
    for ls in p.findall("hp:linesegarray", NS):
        p.remove(ls)


def make_para(text=None, charpr=BODY_CHARPR, parapr=BODY_PARAPR):
    p = etree.Element(HP + "p", {"id": "0", "paraPrIDRef": parapr, "styleIDRef": "0",
                                 "pageBreak": "0", "columnBreak": "0", "merged": "0"})
    run = etree.SubElement(p, HP + "run", {"charPrIDRef": charpr})
    if text is not None:
        t = etree.SubElement(run, HP + "t")
        t.text = text
    return p


def set_para_text(p, text, charpr):
    """문단의 런을 모두 지우고 텍스트 1개 런으로(빈 문자열이면 빈 런)."""
    for run in p.findall("hp:run", NS):
        p.remove(run)
    run = etree.Element(HP + "run", {"charPrIDRef": str(charpr)})
    if text:
        t = etree.SubElement(run, HP + "t")
        t.text = text
    ls = p.find("hp:linesegarray", NS)
    if ls is not None:
        ls.addprevious(run)
    else:
        p.append(run)
    drop_lineseg(p)


def tables_in(p):
    return [r.find("hp:tbl", NS) for r in p.findall("hp:run", NS) if r.find("hp:tbl", NS) is not None]


def cell(tbl, r, c):
    for tc in tbl.findall("hp:tr/hp:tc", NS):
        a = tc.find("hp:cellAddr", NS)
        if int(a.get("rowAddr")) == r and int(a.get("colAddr")) == c:
            return tc
    raise KeyError(f"셀 r{r}c{c} 없음")


def cell_paras(tc):
    return tc.find("hp:subList", NS).findall("hp:p", NS)


def row0_texts(tbl):
    out = []
    for tc in tbl.findall("hp:tr/hp:tc", NS):
        if tc.find("hp:cellAddr", NS).get("rowAddr") == "0":
            out.append(norm(all_text(tc)))
    return out


class CharPrInfo:
    """header.xml 문자 모양 색 조회(검정 런 고르기용)."""

    def __init__(self, header_xml: bytes):
        root = etree.fromstring(header_xml)
        self.color = {cp.get("id"): cp.get("textColor") for cp in root.iter("{%s}charPr" % NS["hh"])}

    def black(self, cid):
        return (self.color.get(str(cid)) or "#000000").upper() == "#000000"


# ───────────────────────── 편집 본체 ─────────────────────────
def edit_section(xml: bytes, header: bytes, log=print):
    root = etree.fromstring(xml)
    cpi = CharPrInfo(header)

    def paras():
        return root.findall("hp:p", NS)

    anchors = []

    # (a) 표지 '<작성 시 주의 사항>' 박스 + 작성요령 박스 삭제
    n_box = 0
    for p in list(paras()):
        for tbl in tables_in(p):
            tx = norm(all_text(tbl))
            if tx.startswith("<작성 시 주의 사항>") or tx.startswith("작성요령"):
                others = [t for t in tables_in(p) if t is not tbl]
                if not others and not own_text(p).strip():
                    root.remove(p)
                else:
                    p.remove(tbl.getparent())
                    drop_lineseg(p)
                n_box += 1
                break
    log(f"  삭제: 작성요령·주의사항 박스 {n_box}개")

    # 강제 쪽 나눔 해제, 작성요령이 빠진 자리 빈 문단 정리
    for p in paras():
        if any(norm(own_text(p)).startswith(norm(h)) for h in UNBREAK):
            p.set("pageBreak", "0")
    for head in TIGHTEN_AFTER:
        ps = paras()
        for i, p in enumerate(ps):
            if norm(own_text(p)).startswith(norm(head)):
                j = i + 1
                while j < len(ps) and is_empty_para(ps[j]):
                    root.remove(ps[j])
                    j += 1
                break

    # (b-1) 표지 값 칸
    cover = tables_in(paras()[0])[0]

    def black_cp(runs, fallback=BODY_CHARPR):
        blacks = [r_.get("charPrIDRef") for r_ in runs if cpi.black(r_.get("charPrIDRef"))]
        return blacks[-1] if blacks else fallback

    def put(r, c, text, *, keep=None, append=False, charpr=None):
        tc = cell(cover, r, c)
        ps = cell_paras(tc)
        if append:                       # 안내문 아래 새 문단
            newp = copy.deepcopy(ps[-1])
            set_para_text(newp, text, charpr or "42")   # 42: 맑은 고딕 9pt 검정
            ps[-1].addnext(newp)
            return
        p = ps[0]
        runs = p.findall("hp:run", NS)
        if keep is not None:             # 기존 문구 일부를 토큰으로 치환
            txt = own_text(p)
            if keep not in txt:
                raise RuntimeError(f"표지 r{r}c{c}에 '{keep}' 없음: {txt!r}")
            set_para_text(p, txt.replace(keep, text, 1), charpr or runs[0].get("charPrIDRef"))
        else:
            set_para_text(p, text, charpr or black_cp(runs))

    def note(token, where, kind="cell"):
        anchors.append({"token": token, "where": where, "kind": kind})

    put(2, 2, "{{CV_ORG}}"); note("{{CV_ORG}}", "표지 신청기관 기관명")
    put(2, 7, "대학({{CV_UNIV}}), 출연(연)({{CV_GRI}})", keep="대학(    ), 출연(연) (    )")
    note("{{CV_UNIV}}", "표지 기관구분 '대학( )' 괄호 안(해당 시 'O' 또는 '√')")
    note("{{CV_GRI}}", "표지 기관구분 '출연(연)( )' 괄호 안(해당 없으면 '  ')")
    put(3, 2, "{{CV_ADDR}}"); note("{{CV_ADDR}}", "표지 신청기관 주소")
    put(4, 2, "{{CV_TEAM_KO}}")
    note("{{CV_TEAM_KO}}", "표지 탐색팀명 국문(띄어쓰기 포함 10자 이내 — '(제출 시 삭제)' 안내문은 마스터에서 삭제)")
    put(5, 2, "{{CV_TEAM_EN}}"); note("{{CV_TEAM_EN}}", "표지 탐색팀명 영문")
    put(9, 2, "{{CV_ITEM_KO}}"); note("{{CV_ITEM_KO}}", "표지 아이템명 국문")
    put(10, 2, "{{CV_ITEM_EN}}"); note("{{CV_ITEM_EN}}", "표지 아이템명 영문")
    put(11, 2, "{{CV_FIELD}}", append=True)
    note("{{CV_FIELD}}", "표지 창업아이템 기술분야 — 파란 안내문('예) IT, NT…') 아래 새 줄(IT/BT/NT/ET/ST/CT/기타 중 1)")
    put(11, 6, "제조업({{CV_MFG}}), 비제조업({{CV_NONMFG}})", keep="제조업(   ),  비제조업(    )")
    note("{{CV_MFG}}", "표지 업종 '제조업( )' 괄호 안")
    note("{{CV_NONMFG}}", "표지 업종 '비제조업( )' 괄호 안")
    for role, r0 in ROLE_ROWS.items():
        for dr, c, suf, desc in ROLE_FIELDS:
            tok = "{{%s_%s}}" % (role, suf)
            if suf == "NAME":
                put(r0 + dr, c, tok + "  (서명)", keep="(서명)")
            else:
                put(r0 + dr, c, tok)
            extra = " — 양식 예시('<예> 석사과정/…')는 삭제" if (role, suf) == ("EL", "DEGREE") else ""
            note(tok, f"표지 {role} {desc}{extra}")
    date_tc = cell(cover, 24, 0)
    for p in cell_paras(date_tc):
        if "2026년  월   일" in own_text(p):
            set_para_text(p, own_text(p).replace("2026년  월   일", "{{CV_DATE}}"),
                          p.findall("hp:run", NS)[0].get("charPrIDRef"))
            break
    else:
        raise RuntimeError("표지 제출일 문단을 찾지 못함")
    note("{{CV_DATE}}", "표지 하단 제출일('2026년 1월 15일' 형식)")

    # (b-2) 본문 앵커
    for head, tok, mode, where in SECTION_ANCHORS:
        ps = paras()
        idx = next((i for i, p in enumerate(ps) if norm(own_text(p)).startswith(norm(head))), None)
        if idx is None:
            raise RuntimeError(f"제목을 찾지 못함: {head}")
        coll, j = [], idx + 1
        if mode.startswith("until:"):
            stop = norm(mode.split(":", 1)[1])
            while j < len(ps) and not norm(own_text(ps[j])).startswith(stop):
                coll.append(ps[j]); j += 1
        else:
            while j < len(ps) and is_empty_para(ps[j]):
                coll.append(ps[j]); j += 1
        nxt = ps[j] if j < len(ps) else None
        keep_spacer = nxt is not None and nxt.get("pageBreak") != "1"   # 쪽 나눔 직전 여백은 빈 쪽 위험
        for p in coll:
            root.remove(p)
        tokp = make_para("{{%s}}" % tok)
        ps[idx].addnext(tokp)
        if keep_spacer:
            tokp.addnext(make_para(None))
        anchors.append({"token": "{{%s}}" % tok, "where": where, "kind": "para", "heading": head})
    log(f"  본문 앵커 {len(SECTION_ANCHORS)}개")

    # (b-3) 고정 표
    fixed = [
        ("T_PATENTS", lambda h: h[:1] == ["특허명"], (1, 0),
         "Ⅱ-2-1 '□ 특허 출원/등록 실적' 표 첫 데이터행 첫 셀(9열: 특허명·출원년도·출원국·출원번호·출원인·등록년도·등록국·등록번호·등록인)"),
        ("T_OTHERIP", lambda h: bool(h) and h[0].startswith("유형"), (1, 0),
         "Ⅱ-2-1 '□ 기타 지식재산권' 표 첫 데이터행 첫 셀(5열: 유형·제목·등록년도·권리인·등록번호)"),
        ("T_IPREL", lambda h: "출원 또는 등록번호" in h, (1, 0),
         "Ⅱ-2-1 '□ 핵심기술의 권리인 및 발명자와의 관계' 표 첫 데이터행 첫 셀(6열)"),
        ("T_TEAM", lambda h: h[:3] == ["구분", "성명", "생년월일"], (1, 1),
         "Ⅳ-1 탐색팀 구성 표 EL 행 '성명' 셀(9열, 첫 열 라벨 EL/PM/PI/EM 유지)"),
        ("T_CAREER", lambda h: h[:4] == ["구분", "성명", "소속", "전공분야"], (1, 1),
         "Ⅳ-2 주요 경력 및 역할 표 EL 행 '성명' 셀(6열, 첫 열 라벨 유지)"),
    ]
    all_tbls = [t for p in paras() for t in tables_in(p)]
    for tok, match, (r, c), where in fixed:
        tbl = next((t for t in all_tbls if match(row0_texts(t))), None)
        if tbl is None:
            raise RuntimeError(f"고정 표를 찾지 못함: {tok}")
        for tc in tbl.findall("hp:tr/hp:tc", NS):          # 표 안 예시 텍스트 삭제
            if tc.find("hp:cellAddr", NS).get("rowAddr") == "0":
                continue
            for p in cell_paras(tc):
                tx = norm(own_text(p))
                if tx.startswith("<예>") or tx == "-":
                    set_para_text(p, "", black_cp(p.findall("hp:run", NS)))
        p0 = cell_paras(cell(tbl, r, c))[0]
        set_para_text(p0, "{{%s}}" % tok, black_cp(p0.findall("hp:run", NS)))
        labels = []
        for rr in range(1, int(tbl.get("rowCnt"))):
            try:
                labels.append(norm(all_text(cell(tbl, rr, 0))))
            except KeyError:
                labels.append("")
        anchors.append({"token": "{{%s}}" % tok, "where": where, "kind": "table_first_cell",
                        "data_rows": int(tbl.get("rowCnt")) - 1, "cols": int(tbl.get("colCnt")),
                        "header": row0_texts(tbl), "first_col_labels": labels if c == 1 else None})

    # (b-4) TRL 9칸
    trl = next((t for t in all_tbls if row0_texts(t)[:1] and row0_texts(t)[0].replace(" ", "") == "연구단계(선택)"), None)
    if trl is None:
        raise RuntimeError("TRL 표를 찾지 못함")
    r0 = sorted((tc for tc in trl.findall("hp:tr/hp:tc", NS) if tc.find("hp:cellAddr", NS).get("rowAddr") == "0"),
                key=lambda tc: int(tc.find("hp:cellAddr", NS).get("colAddr")))[1:]
    if len(r0) != 9:
        raise RuntimeError(f"TRL 칸 수 {len(r0)} ≠ 9")
    for n, tc in enumerate(r0, 1):
        p = cell_paras(tc)[0]
        set_para_text(p, own_text(p).replace("(    )", "{{TRL_%d}}" % n),
                      p.findall("hp:run", NS)[0].get("charPrIDRef"))
        anchors.append({"token": "{{TRL_%d}}" % n, "where": f"Ⅱ-2-2 TRL 표 '연구단계(선택)' {n}단계 칸('(    )' 자리)",
                        "kind": "trl"})

    out = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return out, anchors


def repack(src_hwpx: Path, dst_hwpx: Path, new_section: bytes):
    """hwpx 재패키징 — mimetype 첫 항목·무압축(OCF 규약)."""
    with zipfile.ZipFile(src_hwpx) as zf:
        names = zf.namelist()
        blobs = {n: zf.read(n) for n in names}
    blobs[SECTION] = new_section
    order = (["mimetype"] if "mimetype" in blobs else []) + [n for n in names if n != "mimetype"]
    with zipfile.ZipFile(dst_hwpx, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in order:
            if n == "mimetype":
                zi = zipfile.ZipInfo("mimetype")
                zi.compress_type = zipfile.ZIP_STORED
                zf.writestr(zi, blobs[n])
            else:
                zf.writestr(n, blobs[n])


def build(src=DEF_SRC, out_dir=DEF_OUT, preview=DEF_PREVIEW, log=print):
    src, out_dir = Path(src).resolve(), Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    master = out_dir / "template_master.hwpx"
    with tempfile.TemporaryDirectory(prefix="tp_master_") as td:
        td = Path(td)
        work_hwp = td / "orig.hwp"
        shutil.copy2(src, work_hwp)                  # 원본은 읽기만
        raw, edited = td / "raw.hwpx", td / "edited.hwpx"
        log("1) 원본 hwp → hwpx")
        with hf.Hwp() as h:
            h.open(work_hwp)
            h.save_as(raw, "HWPX")
        log("2) section0.xml 편집")
        with zipfile.ZipFile(raw) as zf:
            xml, header = zf.read(SECTION), zf.read(HEADER)
        new_xml, anchors = edit_section(xml, header, log)
        repack(raw, edited, new_xml)
        log("3) 한글로 열어 정규화 저장")
        with hf.Hwp() as h:
            h.open(edited)
            body = h.text()
            missing = [a["token"] for a in anchors if a["token"] not in body]
            if missing:
                raise RuntimeError(f"정규화 후 토큰 누락: {missing}")
            for bad in ("작성요령", "제출 시 삭제", "<작성 시 주의 사항>", "<예>"):
                if bad in body:
                    raise RuntimeError(f"삭제 대상 문구가 남아 있음: {bad}")
            # 양식 제목·표 제목에 '다음 문단과 함께' — 채운 뒤 제목만 쪽 끝에 홀로 남는 것 방지
            kept = 0
            for title in KEEP_WITH_NEXT:
                if not h.find(title):
                    log(f"  (keep-with-next 대상 못 찾음: {title})")
                    continue
                h.para(keep_next=True)
                kept += 1
                # 바로 다음 문단이 빈 여백 문단이면 그것도 묶는다(제목→빈 줄→본문 사슬이 끊기지 않게)
                h.run("Cancel")
                lst, para, _ = h.pos()
                if h.set_pos(lst, para + 1, 0):
                    h.run("MoveParaEnd")
                    if h.pos()[2] == 0:
                        h.para(keep_next=True)
            h.run("Cancel", "MoveDocBegin")
            log(f"  다음 문단과 함께: 제목 {kept}개")
            h.save_as(master, "HWPX")
            pages = h.page_count()
            if preview:
                preview = Path(preview).resolve()
                preview.mkdir(parents=True, exist_ok=True)
                h.save_pdf(preview / "template_master.pdf")
    with zipfile.ZipFile(master) as zf:                # 정규화본 재검증(토큰이 런으로 쪼개지지 않았는지)
        flat = re.sub(r"<[^>]+>", "", zf.read(SECTION).decode("utf-8"))
    lost = [a["token"] for a in anchors if a["token"] not in flat]
    if lost:
        raise RuntimeError(f"저장된 마스터 XML에서 토큰이 쪼개짐/누락: {lost}")
    meta = {
        "master": master.name,
        "source": src.name,
        "pages_empty": pages,
        "token_format": "{{NAME}}",
        "checkboxes": CHECKBOXES,
        "checkbox_rule": "토큰 없이 양식 그대로 둔다 — 채움 단계 replacements에서 '□충청권'→'■충청권'처럼 텍스트 치환",
        "section_tokens": [a["token"].strip("{}") for a in anchors if a["kind"] == "para"],
        "qa_headings": [h for h, *_ in SECTION_ANCHORS],
        "notes": [
            "작성요령 박스 11개(본문 9 + Ⅳ 표 위 2)와 표지 '<작성 시 주의 사항>' 박스, 표지 국문 팀명 '(제출 시 삭제)' 안내문 삭제",
            "남긴 양식 주석: Ⅱ-2-1 표 아래 '※ 핵심기술의 지식재산권 현황…' 3줄, TRL '※ TRL 9단계…', Ⅳ '※ EL 또는 EM이 졸업생일 경우…' 박스·주석 2줄",
            "Ⅰ-2의 '□ 창업(탐색) 아이템의 컨셉/목표 고객/차별성/시장전망' 소제목은 제거 — sections.S_I2의 heading 블록으로 쓴다",
            "'□ 핵심기술의 권리인 및 발명자와의 관계' 앞 강제 쪽 나눔 해제(Ⅲ·Ⅳ 장 시작 쪽 나눔은 유지)",
            "표 안 예시('<예> 석사수료 / 박사과정중', '<예> 학부과정중', '-')와 표지 EL 학위 예시 삭제",
            "기술분야 칸은 파란 안내문을 남기고 그 아래 줄에 {{CV_FIELD}}",
            "본문 앵커 문단은 맑은 고딕 10pt(charPr 9)·문단모양 3 — 채움 엔진이 블록마다 글자·문단 모양을 다시 지정",
        ],
        "anchors": anchors,
    }
    (out_dir / "anchors.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"✅ 마스터: {master}  (빈 양식 {pages}쪽, 토큰 {len(anchors)}개)")
    if preview:
        try:
            import pymupdf as fitz
        except ImportError:  # 구버전
            import fitz
        with fitz.open(str(preview / "template_master.pdf")) as d:
            for i, pg in enumerate(d):
                pg.get_pixmap(dpi=80).save(str(preview / f"page-{i + 1:02d}.png"))
        log(f"   미리보기: {preview}")
    return {"master": str(master), "anchors": str(out_dir / "anchors.json"), "pages": pages,
            "tokens": len(anchors)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="신청서 원본 hwp → 템플릿 마스터 hwpx")
    ap.add_argument("--src", default=str(DEF_SRC))
    ap.add_argument("--out-dir", default=str(DEF_OUT))
    ap.add_argument("--preview", default=str(DEF_PREVIEW), help="미리보기 PDF/PNG 폴더('' 이면 생략)")
    a = ap.parse_args(argv)
    r = build(a.src, a.out_dir, a.preview or None)
    print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
