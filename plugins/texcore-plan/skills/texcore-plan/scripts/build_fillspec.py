# -*- coding: utf-8 -*-
"""초안(07_draft_v2.json 또는 04_draft_v1.json) + 그림 렌더 결과(08_figures/figures_report.json)
→ 한글 주입 사양 08_fill_spec.json (hwp_fill.py 계약).

결정적 변환만 한다(내용 판단 없음):
- cover → {{CV_*}} {{EL_*}} 치환 + 체크박스(□→■) 치환
- sections[].blocks → 섹션 앵커별 블록(figure_ref는 렌더된 PNG 경로로 치환)
- fixed_tables → 고정 표 행, TRL 레벨
- edu_type 국내 → delete_english_section
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANCHORS = HERE.parent / "assets" / "template" / "anchors.json"

# 양식의 체크박스 원문(템플릿 마스터 기준). anchors.json에 "checkboxes"가 있으면 그것을 우선한다.
_DEFAULT_CHECKBOXES = {
    "region": {"수도권": "□수도권", "충청권": "□충청권", "대경권": "□대경권", "호남권": "□호남권", "동남권": "□동남권",
               "여성특화형": "□여성특화형", "출연(연)특화형": "□출연(연)특화형", "파악불가": "□ 신청 실험실창업혁신단 파악 불가"},
    "edu_type": {"해외": "□ 해외교육형", "국내": "□ 국내교육형"},
    "women_item": "□ 여성특화형",
    "gri_item": "□ 출연(연)특화형",
}
FIGURE_DEFAULT_WIDTH_MM = 150.0
FIGURE_SIDE_BY_SIDE_WIDTH_MM = 74.0

def _load(p: Path) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))

def _checkboxes() -> dict:
    """anchors.json의 checkboxes가 {region:{…},edu_type:{…},…} 사전이면 그것을, 문자열 목록이면 기본 매핑을 쓴다."""
    if ANCHORS.exists():
        a = _load(ANCHORS)
        cb = a.get("checkboxes") if isinstance(a, dict) else None
        if isinstance(cb, dict) and "region" in cb:
            return cb
        if isinstance(cb, list):  # 마스터에 실제로 있는 문자열인지 확인만
            missing = [s for grp in _DEFAULT_CHECKBOXES.values() for s in (grp.values() if isinstance(grp, dict) else [grp]) if s not in cb]
            if missing:
                print(f"[경고] anchors.json checkboxes에 없는 체크박스 문자열: {missing}")
    return _DEFAULT_CHECKBOXES

def _person_tokens(prefix: str, p: dict | None) -> dict:
    p = p or {}
    return {f"{{{{{prefix}_NAME}}}}": p.get("name", ""), f"{{{{{prefix}_BIRTH}}}}": p.get("birth", ""),
            f"{{{{{prefix}_ORG}}}}": p.get("org_dept", ""), f"{{{{{prefix}_MAJOR}}}}": p.get("major", ""),
            f"{{{{{prefix}_DEGREE}}}}": p.get("degree_status", ""), f"{{{{{prefix}_TEL}}}}": p.get("tel", ""),
            f"{{{{{prefix}_PHONE}}}}": p.get("phone", ""), f"{{{{{prefix}_EMAIL}}}}": p.get("email", "")}

def _mark(s: str) -> str:
    """'□수도권' → '■수도권' (첫 □만)."""
    return s.replace("□", "■", 1)

def cover_replacements(cover: dict, edu_type: str) -> dict:
    cb = _checkboxes()
    rep = {
        "{{CV_ORG}}": cover.get("org", ""), "{{CV_ADDR}}": cover.get("address", ""),
        "{{CV_UNIV}}": " O " if cover.get("org_type") == "대학" else "    ",
        "{{CV_GRI}}": " O " if cover.get("org_type") == "출연연" else "    ",
        "{{CV_TEAM_KO}}": cover.get("team_ko", ""), "{{CV_TEAM_EN}}": cover.get("team_en", ""),
        "{{CV_ITEM_KO}}": cover.get("item_ko", ""), "{{CV_ITEM_EN}}": cover.get("item_en", ""),
        "{{CV_FIELD}}": cover.get("tech_field", ""),
        "{{CV_MFG}}": " O " if cover.get("industry") == "제조업" else "   ",
        "{{CV_NONMFG}}": " O " if cover.get("industry") == "비제조업" else "    ",
        "{{CV_DATE}}": cover.get("date") or "2026년    월    일",
    }
    rep.update(_person_tokens("EL", cover.get("EL"))); rep.update(_person_tokens("PM", cover.get("PM"))); rep.update(_person_tokens("PI", cover.get("PI")))
    region = cover.get("region")
    if region in cb["region"]: rep[cb["region"][region]] = _mark(cb["region"][region])
    if edu_type in cb["edu_type"]: rep[cb["edu_type"][edu_type]] = _mark(cb["edu_type"][edu_type])
    if cover.get("women") or region == "여성특화형": rep[cb["women_item"]] = _mark(cb["women_item"])
    if cover.get("gri") or region == "출연(연)특화형": rep[cb["gri_item"]] = _mark(cb["gri_item"])
    return rep

def _figure_block(b: dict, fig_files: dict, fig_meta: dict, ws: Path) -> dict:
    """figure_ref → figure(렌더된 PNG). figure → 경로 절대화."""
    if b.get("type") == "figure_ref":
        fid = b["figure_id"]; meta = fig_meta.get(fid, {})
        path = fig_files.get(fid)
        if not path:
            return {"type": "para", "text": f"[그림 렌더 실패: {fid}] " + (b.get("caption") or "")}
        return {"type": "figure", "caption": b.get("caption") or meta.get("caption", ""),
                "images": [{"path": str(Path(path).resolve()), "width_mm": float(b.get("width_mm") or meta.get("width_mm") or FIGURE_DEFAULT_WIDTH_MM)}],
                "source": b.get("source") or meta.get("source", ""), "proves": b.get("proves") or meta.get("proves", "")}
    imgs = []
    n = len(b.get("images", []))
    for im in b.get("images", []):
        p = Path(im["path"])
        if not p.is_absolute(): p = (ws / p).resolve()
        w = im.get("width_mm") or (FIGURE_SIDE_BY_SIDE_WIDTH_MM if n >= 2 else FIGURE_DEFAULT_WIDTH_MM)
        imgs.append({"path": str(p), "width_mm": float(w)})
    return {"type": "figure", "caption": b.get("caption", ""), "images": imgs, "source": b.get("source", ""), "proves": b.get("proves", "")}

def build(ws: Path, draft_file: Path | None = None) -> Path:
    ws = Path(ws)
    dp = Path(draft_file) if draft_file else (ws / "07_draft_v2.json" if (ws / "07_draft_v2.json").exists() else ws / "04_draft_v1.json")
    doc = _load(dp)
    rep_p = ws / "08_figures" / "figures_report.json"
    fig_files, fig_meta = {}, {}
    if rep_p.exists():
        for r in _load(rep_p) if isinstance(_load(rep_p), list) else _load(rep_p).get("figures", []):
            if r.get("ok") and r.get("file"):
                # report의 file은 파일명만 들어 있다 → 08_figures 기준으로 절대화(현재 폴더 기준 resolve 버그 수정, 2026-10-27 tp-designer)
                fp = Path(r["file"])
                fig_files[r["id"]] = str(fp if fp.is_absolute() else rep_p.parent / fp)
    for f in doc.get("figures", []):
        fig_meta[f["id"]] = {"caption": f.get("caption", ""), "source": f.get("source", ""), "proves": f.get("proves", ""), "width_mm": f.get("width_mm")}
    edu = doc.get("edu_type", "해외")
    spec = {"replacements": cover_replacements(doc.get("cover", {}), edu), "sections": {}, "tables": {}, "trl": {}, "delete_english_section": edu == "국내",
            "font": {"body_pt": 10, "table_pt": 9, "caption_pt": 8.5}}
    for s in doc.get("sections", []):
        blocks = []
        for b in s.get("blocks", []):
            t = b.get("type")
            if t in ("figure", "figure_ref"): blocks.append(_figure_block(b, fig_files, fig_meta, ws))
            elif t == "table":
                blocks.append({k: v for k, v in b.items() if k in ("type", "caption", "columns", "rows", "col_widths_mm", "source", "font_pt")})
            elif t in ("heading", "subheading", "para", "callout"): blocks.append({"type": t, "text": b.get("text", "")})
            elif t == "bullets": blocks.append({"type": "bullets", "items": list(b.get("items", []))})
            elif t == "spacer": blocks.append({"type": "spacer"})
        spec["sections"][s["id"]] = blocks
    ft = doc.get("fixed_tables", {})
    spec["tables"] = {
        "T_PATENTS": {"rows": ft.get("patents", []), "delete_if_empty": True},
        "T_OTHERIP": {"rows": ft.get("other_ip", []), "delete_if_empty": True},
        "T_IPREL": {"rows": ft.get("ip_relations", []), "delete_if_empty": False},
        "T_TEAM": {"rows": ft.get("team_members", []), "keep_first_col": True},
        "T_CAREER": {"rows": ft.get("team_careers", []), "keep_first_col": True},
    }
    spec["trl"] = {"level": int((ft.get("trl") or {}).get("level") or 0) or None}
    # 재빌드해도 유지돼야 하는 주입 옵션(remove_page_breaks·clear_unfilled·font 덮어쓰기)은 08_fill_options.json에 둔다
    opt_p = ws / "08_fill_options.json"
    if opt_p.exists():
        opts = _load(opt_p)
        for k in ("remove_page_breaks", "clear_unfilled"):
            if k in opts: spec[k] = bool(opts[k])
        if isinstance(opts.get("font"), dict): spec["font"].update(opts["font"])
        # 고정 표별 글자 크기(예: {"T_CAREER": 8.5}) — 경력 표가 길어 쪽을 넘길 때
        for tname, pt in (opts.get("table_font_pt") or {}).items():
            if tname in spec["tables"]: spec["tables"][tname]["font_pt"] = float(pt)
    out = ws / "08_fill_spec.json"
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return out

if __name__ == "__main__":
    import sys
    print(build(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None))
