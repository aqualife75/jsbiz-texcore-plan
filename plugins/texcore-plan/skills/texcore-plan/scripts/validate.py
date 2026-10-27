# -*- coding: utf-8 -*-
"""JSON 스키마 + 필드 규칙 검증(texcore-plan). 빈 리스트 = 통과.

validate_phase(ws, target)  → 오류 목록(게이트를 막는 것)
lint(obj, target)           → 경고 목록(막지는 않지만 writer가 고쳐야 하는 것: 긴 문장·경고어·결론 박스 없음)
"""
from __future__ import annotations
import json, re
from pathlib import Path
import jsonschema

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
SCHEMAS = ASSETS / "schemas"
_NUM = re.compile(r"\d")

SLOT_IDS = ["I-1", "I-2a", "I-2b", "I-2c", "I-2d", "II-1", "II-2a", "II-2b", "III-1", "III-2", "III-3", "IV", "EN"]
CORE_SECTIONS = ["S_I1", "S_I2", "S_II1", "S_II2_PLAN", "S_II2_UPGRADE", "S_III1", "S_III2", "S_III3"]
EN_SECTIONS = ["S_EN1", "S_EN2", "S_EN3"]
CALLOUT_SECTIONS = {"S_I1", "S_I2", "S_II1", "S_III1", "S_III2"}  # 결론 박스가 맨 앞에 와야 하는 본문 섹션
FIGURE_TYPES = {"competitor_matrix", "tam_sam_som", "tech_concept", "trl_ladder", "gantt_milestones", "cost_table", "team_org",
                "evidence_card", "evidence_board", "kpi_strip", "prototype_stages", "customer_profile"}

_TARGET_FILES = {
    "fact_pack": "02_fact_pack.json", "image_catalog": "01_extract/image_catalog.json", "outline": "03_outline.json",
    "draft": "04_draft_v1.json", "draft_v2": "07_draft_v2.json", "review": "05_review/summary.json",
    "evidence": "06_evidence/evidence.json", "ledger": "06_evidence/image_ledger.json",
}
_SCHEMA_OF = {"review": "review_summary", "ledger": "image_ledger", "draft_v2": "draft"}

def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))

def load_limits() -> dict:
    return json.loads((ASSETS / "limits.json").read_text(encoding="utf-8"))

def load_banned() -> dict:
    return json.loads((ASSETS / "banned_phrases.json").read_text(encoding="utf-8"))

def _schema_errors(obj, name) -> list[str]:
    v = jsonschema.Draft7Validator(_load_schema(name))
    return [f"[schema:{name}] {'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in sorted(v.iter_errors(obj), key=lambda e: [str(x) for x in e.absolute_path])]

# ───────────────────────── 규칙 ─────────────────────────
def _rules_fact_pack(fp: dict) -> list[str]:
    errs = []
    ids = [s["slot_id"] for s in fp.get("slots", [])]
    if sorted(ids) != sorted(SLOT_IDS):
        errs.append(f"slots: 13개 슬롯 id가 각 1개씩 있어야 함 (현재 {ids})")
    for s in fp.get("slots", []):
        for i, f in enumerate(s.get("facts", [])):
            if _NUM.search(f.get("text", "")) and not f.get("source", "").strip():
                errs.append(f"slot {s['slot_id']} facts[{i}]: 숫자가 있는데 source 비어 있음")
    for g in fp.get("gaps", []):
        if not g.get("question_to_team", "").strip():
            errs.append(f"gaps '{g.get('item')}': question_to_team(팀에게 보낼 질문) 비어 있음")
    return errs

def _required_sections(doc: dict) -> list[str]:
    return CORE_SECTIONS + (EN_SECTIONS if doc.get("edu_type") == "해외" else [])

def _rules_outline(doc: dict) -> list[str]:
    errs = []
    ids = [s["id"] for s in doc.get("sections", [])]
    for sid in _required_sections(doc):
        if sid not in ids: errs.append(f"outline: 섹션 {sid} 없음")
    lim = load_limits()
    budget = sum(float(s.get("page_budget", 0)) for s in doc.get("sections", []))
    if budget > lim["page_total_max"] - lim["page_budget"]["cover"] + 0.01:
        errs.append(f"outline: 본문 쪽 예산 합 {budget:.1f} > {lim['page_total_max'] - lim['page_budget']['cover']} (표지 제외)")
    fig_ids = {f["id"] for f in doc.get("figures_plan", [])}
    for s in doc.get("sections", []):
        for fid in s.get("figure_ids", []):
            if fid not in fig_ids: errs.append(f"outline {s['id']}: figure_ids '{fid}'가 figures_plan에 없음")
    return errs

def _block_texts(b: dict):
    """블록 안의 모든 본문 문자열을 (필드명, 문자열)로."""
    for k in ("text", "caption", "source", "proves"):
        if b.get(k): yield k, b[k]
    for i, it in enumerate(b.get("items", []) or []): yield f"items[{i}]", it
    for c in b.get("columns", []) or []: yield "columns", c
    for r in b.get("rows", []) or []:
        for c in r: yield "rows", c

def _rules_draft(doc: dict) -> list[str]:
    errs = []
    lim = load_limits(); bl = lim["block"]; banned = load_banned()["banned"]
    ids = [s["id"] for s in doc.get("sections", [])]
    for sid in _required_sections(doc):
        if sid not in ids: errs.append(f"draft: 섹션 {sid} 없음")
    if doc.get("edu_type") == "국내" and any(i in EN_SECTIONS for i in ids):
        errs.append("draft: 국내교육형은 영문 요약(S_EN*)을 쓰지 않음 — 삭제")
    fig_ids = {f["id"] for f in doc.get("figures", [])}
    for f in doc.get("figures", []):
        if f.get("type") not in FIGURE_TYPES: errs.append(f"figures '{f['id']}': 알 수 없는 type '{f.get('type')}'")
    is_v2 = doc.get("changes") is not None
    for s in doc.get("sections", []):
        sid = s["id"]; n_fig = 0; chars = 0
        for bi, b in enumerate(s.get("blocks", [])):
            t = b.get("type")
            if t == "figure_ref":
                n_fig += 1
                if b.get("figure_id") not in fig_ids: errs.append(f"{sid} blocks[{bi}]: figure_ref '{b.get('figure_id')}' 없음")
            elif t == "figure":
                n_fig += 1
                if not b.get("images"): errs.append(f"{sid} blocks[{bi}]: figure에 images 없음")
                if not (b.get("caption") or "").strip(): errs.append(f"{sid} blocks[{bi}]: figure caption 없음(그림마다 [그림 n] 캡션 필수)")
            elif t == "table":
                if not b.get("columns") or not b.get("rows"): errs.append(f"{sid} blocks[{bi}]: table에 columns/rows 필요")
                elif len(b["rows"]) > bl["max_table_rows"]: errs.append(f"{sid} blocks[{bi}]: 표 행 {len(b['rows'])} > {bl['max_table_rows']}")
                elif len(b["columns"]) > bl["max_table_cols"]: errs.append(f"{sid} blocks[{bi}]: 표 열 {len(b['columns'])} > {bl['max_table_cols']}")
            elif t == "bullets" and len(b.get("items", [])) > bl["max_bullets_per_block"]:
                errs.append(f"{sid} blocks[{bi}]: 불릿 {len(b['items'])}개 > {bl['max_bullets_per_block']}")
            for field, txt in _block_texts(b):
                chars += len(txt)
                mx = {"heading": bl["heading"], "subheading": bl["subheading"], "para": bl["para"], "callout": bl["callout"]}.get(t)
                if field == "text" and mx and len(txt) > mx:
                    errs.append(f"{sid} blocks[{bi}] {t}: {len(txt)}자 > 상한 {mx}자 — '{txt[:24]}…'")
                if field.startswith("items") and len(txt) > bl["bullet_item"]:
                    errs.append(f"{sid} blocks[{bi}] {field}: {len(txt)}자 > {bl['bullet_item']}자")
                if field == "rows" and len(txt) > bl["table_cell"]:
                    errs.append(f"{sid} blocks[{bi}] 표 셀 {len(txt)}자 > {bl['table_cell']}자 — '{txt[:20]}…'")
                for ph in banned:
                    if ph in txt: errs.append(f"{sid} blocks[{bi}] {field}: 금지 표현 '{ph}' — 구체 명사·숫자로 바꿀 것")
                if is_v2 and "[기입 필요" in txt:
                    errs.append(f"{sid} blocks[{bi}] {field}: 개정본에 [기입 필요] 잔존 — 채우거나 [확보 필요]로")
        need = lim["evidence_figures_min"].get(sid, 0)
        if n_fig < need: errs.append(f"{sid}: 증거 그림/도식 {n_fig}개 < 최소 {need}개 (심사위원이 글 대신 그림으로 판단하게 할 것)")
        if n_fig > lim["figures_per_section_max"]: errs.append(f"{sid}: 그림 {n_fig}개 > 최대 {lim['figures_per_section_max']}개")
        mx_chars = lim["section_chars"].get(sid)
        if mx_chars and chars > mx_chars: errs.append(f"{sid}: 본문 {chars}자 > 상한 {mx_chars}자 (쪽 예산 초과 위험) — 문장을 줄이거나 표·그림으로")
    ft = doc.get("fixed_tables", {})
    for i, r in enumerate(ft.get("team_members", [])):
        if r and r[0] not in ("EL", "PM", "PI", "EM"): errs.append(f"team_members[{i}]: 첫 칸은 EL/PM/PI/EM 중 하나")
    for i, r in enumerate(ft.get("team_careers", [])):
        if r and r[0] not in ("EL", "PM", "PI", "EM"): errs.append(f"team_careers[{i}]: 첫 칸은 EL/PM/PI/EM 중 하나")
    return errs

def _rules_review(doc: dict) -> list[str]:
    errs = []
    sc = doc.get("item_scores", {})
    tot = sum(float(sc.get(k, 0)) for k in ("아이템", "핵심기술", "사업화", "팀", "참여의지"))
    if abs(tot - float(sc.get("total", -1))) > 0.6: errs.append(f"item_scores.total({sc.get('total')})이 항목 합({tot:.1f})과 다름")
    return errs

_RULES = {"fact_pack": _rules_fact_pack, "outline": _rules_outline, "draft": _rules_draft, "review_summary": _rules_review}

# ───────────────────────── 경고(lint) ─────────────────────────
_SENT_SPLIT = re.compile(r"(?<=[.다!?])\s+|(?<=다\.)")

def lint(doc: dict, target: str) -> list[str]:
    """draft 전용: 긴 문장·경고 표현·결론 박스·영문 분량. 게이트를 막지 않는다."""
    if target not in ("draft", "draft_v2"): return []
    lim = load_limits(); warn_words = load_banned()["warn"]; out = []
    for s in doc.get("sections", []):
        sid = s["id"]; blocks = s.get("blocks", [])
        if sid in CALLOUT_SECTIONS and blocks and blocks[0].get("type") != "callout":
            out.append(f"{sid}: 첫 블록이 callout(한 줄 결론)이 아님 — 심사위원이 먼저 읽을 결론 박스를 맨 앞에")
        wc = {}
        for bi, b in enumerate(blocks):
            for field, txt in _block_texts(b):
                if b.get("type") in ("para", "callout") or field.startswith("items"):
                    for sent in re.split(r"(?<=다\.)|(?<=요\.)|(?<=\.)\s", txt):
                        sent = sent.strip()
                        if len(sent) > lim["sentence_max_chars"]:
                            out.append(f"{sid} blocks[{bi}]: 문장 {len(sent)}자 > {lim['sentence_max_chars']}자 — 둘로 나눌 것: '{sent[:30]}…'")
                for w in warn_words:
                    if w in txt: wc[w] = wc.get(w, 0) + txt.count(w)
        for w, n in wc.items():
            if n >= 3: out.append(f"{sid}: 경고 표현 '{w}' {n}회 — 구체 명사로 바꿀 것")
        if sid.startswith("S_EN"):
            txt = " ".join(t for b in blocks for _, t in _block_texts(b))
            if len(txt) > 500: out.append(f"{sid}: 영문 {len(txt)}자 > 500자 제한")
    return out

def validate_obj(obj: dict, schema_name: str) -> list[str]:
    errs = _schema_errors(obj, schema_name)
    if not errs and schema_name in _RULES:
        errs += _RULES[schema_name](obj)
    return errs

def validate_phase(ws: Path, target: str, file: Path | None = None) -> list[str]:
    ws = Path(ws)
    path = Path(file) if file else ws / _TARGET_FILES[target]
    if not path.exists():
        return [f"파일 없음: {path}"]
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return [f"JSON 파싱 실패 {path.name}: {exc}"]
    return validate_obj(obj, _SCHEMA_OF.get(target, target))

def lint_phase(ws: Path, target: str, file: Path | None = None) -> list[str]:
    ws = Path(ws)
    path = Path(file) if file else ws / _TARGET_FILES[target]
    if not path.exists(): return []
    try:
        return lint(json.loads(path.read_text(encoding="utf-8")), target)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
