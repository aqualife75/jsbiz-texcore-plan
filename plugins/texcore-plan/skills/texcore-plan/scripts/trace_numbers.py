# -*- coding: utf-8 -*-
"""초안 본문·그림 데이터의 숫자가 사실 팩/증거 원장에 존재하는지 대조한다(texcore-plan). 미추적 1건이면 실패.

- 검사 대상: sections[].blocks 의 모든 문자열, figures[].data 의 모든 문자열.
- 제외: cover·fixed_tables(팀 자료 전사), 연도(1990~2035), 단위 없는 20 미만 작은 수, [그림 n]/[표 n] 번호.
- 블록에 `calc`(산식)가 있고 산식의 숫자가 전부 허용 목록에 있으면 그 블록의 숫자는 허용([추정] 계산값).
"""
from __future__ import annotations
import json, re
from pathlib import Path

_NUM_RE = re.compile(r"(?<![\w.\-])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*(조|억|만|천|%|p|배|원|명|건|개월|개|년|일|시간|분|초|회|대|곳|명분|B|M|K|USD|달러|달러)?")
_STRICT_UNITS = {"%", "억", "만", "조", "원", "배", "개월", "년", "B", "M", "K", "USD", "달러", "p", "회", "대", "곳"}
_FIG_NO = re.compile(r"\[(그림|표|증거)\s*\d+\]")

def _canon(m: re.Match) -> str | None:
    whole, frac, unit = m.group(1).replace(",", ""), m.group(2), m.group(3) or ""
    tok = whole + (f".{frac}" if frac else "")
    val = float(tok)
    if not frac and 1990 <= val <= 2035 and unit in ("", "년"):
        return None
    if not frac and val < 20 and unit not in _STRICT_UNITS:
        return None
    return tok

def tokens(text: str) -> set[str]:
    out = set()
    for m in _NUM_RE.finditer(_FIG_NO.sub("", text or "")):
        t = _canon(m)
        if t: out.add(t)
    return out

def _all_strings(obj):
    if isinstance(obj, str): yield obj
    elif isinstance(obj, dict):
        for v in obj.values(): yield from _all_strings(v)
    elif isinstance(obj, list):
        for v in obj: yield from _all_strings(v)

def collect_allowed(fact_pack: dict, evidence: dict | None) -> set[str]:
    allowed = set()
    for s in _all_strings(fact_pack): allowed |= tokens(s)
    if evidence:
        for s in _all_strings(evidence): allowed |= tokens(s)
    return allowed

def _calc_ok(calc: str | None, allowed: set[str]) -> bool:
    if not calc: return False
    ct = tokens(calc)
    return bool(ct) and ct <= allowed

def check_draft(doc: dict, allowed: set[str]) -> list[dict]:
    out = []
    for s in doc.get("sections", []):
        sid = s.get("id")
        for bi, b in enumerate(s.get("blocks", [])):
            if _calc_ok(b.get("calc"), allowed): continue
            for txt in _all_strings({k: v for k, v in b.items() if k not in ("calc", "figure_id", "images", "type", "kind", "evidence_ids")}):
                for tok in sorted(tokens(txt)):
                    if tok not in allowed:
                        out.append({"section_id": sid, "field": f"blocks[{bi}]", "token": tok, "context": txt[:70]})
    for f in doc.get("figures", []):
        if _calc_ok(f.get("calc"), allowed): continue
        for txt in _all_strings(f.get("data", {})):
            for tok in sorted(tokens(txt)):
                if tok not in allowed:
                    out.append({"section_id": f.get("section_id"), "field": f"figure {f.get('id')}", "token": tok, "context": txt[:70]})
    return out

def _load_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"JSON 파싱 실패 {Path(path).name}: {exc}") from exc

def run(ws: Path, draft_file: Path | None) -> dict:
    ws = Path(ws)
    fp_path = ws / "02_fact_pack.json"
    if not fp_path.exists():
        raise FileNotFoundError(f"사실 팩 없음: {fp_path} — tp-intake 단계를 먼저 완료하세요")
    fp = _load_json(fp_path)
    ev_path = ws / "06_evidence" / "evidence.json"
    ev = _load_json(ev_path) if ev_path.exists() else None
    if draft_file: sf = Path(draft_file)
    elif (ws / "07_draft_v2.json").exists(): sf = ws / "07_draft_v2.json"
    elif (ws / "04_draft_v1.json").exists(): sf = ws / "04_draft_v1.json"
    else: raise FileNotFoundError("초안 파일 없음 (04_draft_v1.json / 07_draft_v2.json)")
    doc = _load_json(sf)
    allowed = collect_allowed(fp, ev)
    untraced = check_draft(doc, allowed)
    rep = {"draft_file": str(sf), "sections": len(doc.get("sections", [])), "allowed_tokens": len(allowed), "untraced": untraced}
    (ws / "05_review").mkdir(exist_ok=True)
    (ws / "05_review" / "trace_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return rep
