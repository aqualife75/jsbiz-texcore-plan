# -*- coding: utf-8 -*-
"""단계 진입 게이트(texcore-plan).

phase 2  → WRITE   : 사실 팩·이미지 카탈로그 검증
phase 3  → REVIEW  : 초안 v1 검증 + 숫자 추적
phase 4  → RESEARCH: 모의심사 summary 존재
phase 5  → DESIGN  : 초안 v2 검증 + 추적 + [기입 필요] 0 + critical 0(또는 승인)
phase 6  → FINAL   : 09_build/qa_report.md 에 BLOCKING 0
final              : 10_final 산출물 존재 + 최종 추적
"""
from __future__ import annotations
import json, re
from pathlib import Path
import validate, trace_numbers
from state import State

_FINAL_REQUIRED = ["*_사업신청서.hwpx", "*_사업신청서.pdf", "심사대비_패키지.md", "팀_확인사항.md"]

def count_placeholders(draft_file: Path, marker: str = "[기입 필요") -> int:
    try:
        doc = json.loads(Path(draft_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    body = json.dumps({"sections": doc.get("sections", []), "figures": doc.get("figures", []), "cover": doc.get("cover", {}),
                       "fixed_tables": doc.get("fixed_tables", {})}, ensure_ascii=False)
    return len(re.findall(re.escape(marker), body))

def _draft_path(ws: Path) -> Path | None:
    for n in ("07_draft_v2.json", "04_draft_v1.json"):
        if (ws / n).exists(): return ws / n
    return None

def check(ws: Path, phase: str, accept_risk: bool = False) -> tuple[bool, list[str]]:
    ws = Path(ws); reasons: list[str] = []
    st = State.load(ws)
    if accept_risk: st.approve("accept_risk")
    risk_ok = accept_risk or st.data["approvals"].get("accept_risk", False)

    if phase == "2":
        reasons += validate.validate_phase(ws, "fact_pack")
        reasons += validate.validate_phase(ws, "image_catalog")
    elif phase == "3":
        reasons += validate.validate_phase(ws, "draft")
        try:
            rep = trace_numbers.run(ws, ws / "04_draft_v1.json")
            if rep["untraced"]: reasons.append(f"trace: 미추적 숫자 {len(rep['untraced'])}건 (05_review/trace_report.json) — 사실 팩에 없는 숫자는 [기입 필요]로")
        except (FileNotFoundError, ValueError) as exc:
            reasons.append(f"trace: {exc}")
    elif phase == "4":
        if not (ws / "05_review" / "summary.json").exists(): reasons.append("05_review/summary.json 없음 — 모의심사 미완")
        else: reasons += validate.validate_phase(ws, "review")
    elif phase == "5":
        sp = ws / "07_draft_v2.json"
        if not sp.exists(): reasons.append("07_draft_v2.json 없음 — tp-researcher merge 미완")
        else:
            reasons += [f"validate: {e}" for e in validate.validate_phase(ws, "draft_v2", sp)]
            try:
                rep = trace_numbers.run(ws, sp)
                if rep["untraced"]: reasons.append(f"trace: 미추적 숫자 {len(rep['untraced'])}건 (05_review/trace_report.json)")
            except (FileNotFoundError, ValueError) as exc:
                reasons.append(f"trace: {exc}")
            n_fill = count_placeholders(sp)
            if n_fill: reasons.append(f"[기입 필요] {n_fill}건 잔존 — 팀 답변으로 채우거나 [확보 필요]로 옮기세요")
        summ = ws / "05_review" / "summary.json"
        if not summ.exists(): reasons.append("05_review/summary.json 없음")
        else:
            issues = json.loads(summ.read_text(encoding="utf-8")).get("issues", [])
            crit = [i for i in issues if i.get("severity") == "critical" and i.get("status") == "open"]
            if crit and not risk_ok:
                reasons.append(f"critical 미해결 {len(crit)}건: " + "; ".join(i["text"][:40] for i in crit[:5]) + " — 해결하거나 --accept-risk로 승인")
    elif phase == "6":
        qa = ws / "09_build" / "qa_report.md"
        if not qa.exists(): reasons.append("09_build/qa_report.md 없음 — harness qa 미실행")
        elif "BLOCKING: 0" not in qa.read_text(encoding="utf-8"): reasons.append("qa_report에 blocking 결함이 남아 있음(쪽수 초과·토큰 잔존·빈 섹션)")
    elif phase == "final":
        fin = ws / "10_final"
        for pat in _FINAL_REQUIRED:
            if not list(fin.glob(pat)): reasons.append(f"10_final/{pat} 없음")
        sp = _draft_path(ws)
        if sp:
            try:
                if trace_numbers.run(ws, sp)["untraced"]: reasons.append("최종 trace 실패 — 디자인 중 숫자가 바뀌었는지 확인")
            except (FileNotFoundError, ValueError):
                pass
    else:
        reasons.append(f"알 수 없는 phase '{phase}'")

    ok = not reasons
    st.record_gate(phase, ok, reasons); st.save()
    return ok, reasons
