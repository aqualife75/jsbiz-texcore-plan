# -*- coding: utf-8 -*-
"""render_qa.py — 채운 신청서(hwpx/hwp/pdf) → PDF → 쪽별 PNG + 검사 리포트(qa_report.json/.md).

검사
  BLOCKING  10쪽 초과 / 남은 {{토큰}} / '작성요령'·'제출 시 삭제' 문구 잔존
  WARNING   빈 섹션(앵커 제목 아래 본문 없음) / 거의 빈 쪽 / '[기입 필요]'·'[확보 필요]' 라벨 / 영문 섹션 누락
  INFO      쪽수, 쪽별 그림 수, 섹션별 글자 수

CLI
  python render_qa.py --src out.hwpx --out qa_dir [--dpi 110] [--pdf 이미_만든.pdf] [--max-pages 10]
라이브러리
  from render_qa import render
  rep = render(src, out_dir, dpi=110, pdf=None)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

MAX_PAGES = 10
TOKEN_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")
FORBIDDEN = ["작성요령", "작성 요령은 보고서 작성 후 삭제", "제출 시 삭제", "<작성 시 주의 사항>", "제출 시 동 부분 삭제"]
LABELS = ["[기입 필요]", "[확보 필요]", "[자료 없음]"]

# 양식의 구조 제목(문서 순서). (제목, 섹션 키 또는 None, 선택 여부)
HEADINGS = [
    ("Ⅰ. 실험실 창업(탐색) 아이템", None, False),
    ("1. 실험실창업 탐색의 추진 동기와 목표", "S_I1", False),
    ("2. 실험실 창업(탐색) 아이템", "S_I2", False),
    ("Ⅱ. 핵심기술", None, False),
    ("1. 핵심기술의 개요", "S_II1", False),
    ("2. 핵심기술의 확보계획", None, False),
    ("2-1. 핵심기술의 지식재산권 현황", None, False),
    ("2-2. 핵심기술 확보계획", None, False),
    ("□ 핵심기술 확보계획", "S_II2_PLAN", False),
    ("□ 핵심기술의 개발 단계", None, False),
    ("□ 핵심기술 up-grade 계획", "S_II2_UPGRADE", False),
    ("Ⅲ. 사업화 추진계획", None, False),
    ("1. 창업(탐색) 아이템의 시작품(시제품) 제작계획", "S_III1", False),
    ("2. 사업화 추진계획", "S_III2", False),
    ("3. 창업 추진 애로사항 및 건의사항", "S_III3", True),
    ("Ⅳ. 실험실창업탐색팀", None, False),
    ("Summary of Business Start-up Item", None, False),
    ("1) What is the core technology", "S_EN1", False),
    ("2) What is the main problem", "S_EN2", False),
    ("3) What makes your solutions", "S_EN3", False),
]
MIN_SECTION_CHARS = 30


def _fitz():
    try:
        import pymupdf as fitz
    except ImportError:          # 구버전 이름
        import fitz
    return fitz


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def to_pdf(src: Path, pdf: Path) -> Path:
    import hwp_fill as hf
    with hf.Hwp() as h:
        h.open(src)
        h.save_pdf(pdf)
    return pdf


def _sections(full: str):
    """구조 제목 위치로 섹션별 본문 글자 수를 잰다(공백 제거 문자열 기준)."""
    sq = _squash(full)
    found, cur = [], 0
    for title, key, optional in HEADINGS:
        i = sq.find(_squash(title), cur)
        if i >= 0:
            found.append((i, i + len(_squash(title)), title, key, optional))
            cur = i + 1
    out = []
    for k, (s, e, title, key, optional) in enumerate(found):
        if not key:
            continue
        nxt = found[k + 1][0] if k + 1 < len(found) else len(sq)
        body = sq[e:nxt]
        if key == "S_EN2":                       # 2) 질문은 두 줄 — 질문 끝까지 건너뜀
            q = _squash("with this technology, and who are the customers?")
            j = body.find(q)
            if j >= 0:
                body = body[j + len(q):]
        if key == "S_EN1":
            body = body.replace(_squash("you are planning to commercialize?"), "", 1)
        if key == "S_EN3":
            body = body.replace(_squash("better than other (current) solutions?"), "", 1)
        body = re.sub(r"-\d+-", "", body)          # 쪽 번호 '- 3 -' 제거
        out.append({"key": key, "title": title, "chars": len(body), "optional": optional})
    return out, [t for _, _, t, _, _ in found]


def render(src, out_dir, dpi=110, pdf=None, max_pages=MAX_PAGES) -> dict:
    fitz = _fitz()
    src = Path(src).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if pdf:
        pdf = Path(pdf).resolve()
    elif src.suffix.lower() == ".pdf":
        pdf = src
    else:
        pdf = to_pdf(src, out_dir / (src.stem + ".pdf"))

    for old in out_dir.glob("page-*.png"):
        old.unlink()
    pages, full, imgs_per_page = [], [], []
    with fitz.open(str(pdf)) as d:
        n = d.page_count
        for i, pg in enumerate(d):
            pg.get_pixmap(dpi=dpi).save(str(out_dir / f"page-{i + 1:02d}.png"))
            t = pg.get_text(sort=True)          # 위치순 — 기본 순서는 표 안 글(콜아웃 등)을 쪽 끝으로 미룬다
            full.append(t)
            k = len(pg.get_images(full=True))
            imgs_per_page.append(k)
            pages.append({"page": i + 1, "chars": len(_squash(t)), "images": k})
    text = "\n".join(full)

    blocking, warnings, info = [], [], []
    if n > max_pages:
        blocking.append(f"쪽수 {n}쪽 > {max_pages}쪽(표지 포함 10쪽 이내 규정)")
    left = sorted(set(TOKEN_RE.findall(text)))
    if left:
        blocking.append(f"남은 토큰 {len(left)}개: {', '.join(left)}")
    for bad in FORBIDDEN:
        if bad in text:
            blocking.append(f"삭제해야 할 양식 문구 잔존: '{bad}'")
    secs, found = _sections(text)
    for s in secs:
        if s["chars"] < MIN_SECTION_CHARS:
            msg = f"빈 섹션: {s['key']} '{s['title']}' 아래 본문 {s['chars']}자"
            (info if s["optional"] else warnings).append(msg + (" (선택 항목)" if s["optional"] else ""))
    if "Summary of Business Start-up Item" not in found:
        info.append("영문 요약(Summary) 없음 — 국내교육형이면 정상")
    for lab in LABELS:
        c = text.count(lab)
        if c:
            warnings.append(f"라벨 '{lab}' {c}곳 — 팀 확인·기입 필요")
    for p in pages[1:]:
        if p["chars"] < 60 and p["images"] == 0:
            warnings.append(f"{p['page']}쪽이 거의 비어 있음(글자 {p['chars']}자) — 쪽 나눔·표 넘김 확인")
    info.append(f"쪽수 {n}, 그림 {sum(imgs_per_page)}개(쪽별 {imgs_per_page})")

    rep = {
        "src": str(src), "pdf": str(pdf), "pages": n, "max_pages": max_pages,
        "over_limit": n > max_pages, "leftover_tokens": left, "images": sum(imgs_per_page),
        "page_detail": pages, "sections": secs,
        "blocking": blocking, "warnings": warnings, "info": info,
        "pass": not blocking,
        "png": [str(out_dir / f"page-{i + 1:02d}.png") for i in range(n)],
    }
    (out_dir / "qa_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# 신청서 QA 리포트 — {src.name}", "",
          f"- 판정: **{'통과' if rep['pass'] else '차단(BLOCKING)'}**",
          f"- 쪽수: {n} / {max_pages}  ·  그림 {rep['images']}개  ·  남은 토큰 {len(left)}개", ""]
    for title, items in (("BLOCKING", blocking), ("경고", warnings), ("정보", info)):
        md.append(f"## {title} ({len(items)})")
        md += [f"- {x}" for x in items] or ["- 없음"]
        md.append("")
    md += ["## 섹션별 본문 글자 수", "", "| 섹션 | 제목 | 글자 수 |", "|---|---|---|"]
    md += [f"| {s['key']} | {s['title']} | {s['chars']} |" for s in secs]
    md += ["", "## 쪽별", "", "| 쪽 | 글자 | 그림 |", "|---|---|---|"]
    md += [f"| {p['page']} | {p['chars']} | {p['images']} |" for p in pages]
    (out_dir / "qa_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"QA: {n}쪽, BLOCKING {len(blocking)}, 경고 {len(warnings)} → {out_dir / 'qa_report.md'}")
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="신청서 렌더·QA")
    ap.add_argument("--src", required=True, help="hwpx / hwp / pdf")
    ap.add_argument("--out", required=True, help="PNG·리포트 폴더")
    ap.add_argument("--dpi", type=int, default=110)
    ap.add_argument("--pdf", help="이미 만든 PDF(있으면 COM 렌더 생략)")
    ap.add_argument("--max-pages", type=int, default=MAX_PAGES)
    a = ap.parse_args(argv)
    rep = render(a.src, a.out, a.dpi, a.pdf, a.max_pages)
    return 0 if rep["pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
