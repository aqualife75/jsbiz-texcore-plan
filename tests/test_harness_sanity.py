# -*- coding: utf-8 -*-
"""하네스 결정적 모듈 자가 점검: 최소 사실 팩·초안을 만들어 validate/lint/trace/gate/fillspec가 돌아가는지 확인.
사용: python tests/test_harness_sanity.py  (임시 WS는 시스템 temp에 생성)
"""
from __future__ import annotations
import json, sys, tempfile
from pathlib import Path

DEV = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEV / "plugins" / "texcore-plan" / "skills" / "texcore-plan" / "scripts"))
import validate, trace_numbers, gate, build_fillspec  # noqa: E402
from state import State  # noqa: E402

def slot(sid, name, facts, status="partial"):
    return {"slot_id": sid, "name": name, "facts": [{"text": t, "source": "IR.pdf p3", "asof": "2026.04"} for t in facts], "images": [], "status": status}

def main() -> int:
    ws = Path(tempfile.mkdtemp(prefix="tp_sanity_"))
    State.new(ws, team="샘플팀", input_dir=str(ws), edu_type="해외")
    fp = {
        "team": {"name_ko": "샘플팀", "name_en": "Sample", "item_ko": "군집 드론 방제", "item_en": "Swarm drone", "edu_type": "해외", "region": "충청권",
                 "org": "KAIST", "org_type": "대학", "address": "대전", "tech_field": "IT", "industry": "제조업", "one_liner": "농가 방제 시간을 8시간에서 30분으로"},
        "people": {"EL": {"name": "홍길동", "birth": "1990.01.01", "org_dept": "KAIST 항공우주공학과", "major": "항공우주", "degree_status": "박사과정", "tel": "", "phone": "010-0000-0000", "email": "a@b.c"},
                   "PM": {"name": "[자료 없음]"}, "PI": {"name": "김교수"}, "EM": []},
        "slots": [slot("I-1", "동기", ["2025.04 텍스코어 선정"]), slot("I-2a", "컨셉", ["방제 시간 8시간 → 30분"]), slot("I-2b", "고객", ["농가 120곳 인터뷰"]),
                  slot("I-2c", "차별", ["경쟁사 A 가격 4,800만 원"]), slot("I-2d", "시장", ["국내 방제 시장 3,240억 원(2025)"]), slot("II-1", "기술", ["특허 10-2024-0012345"]),
                  slot("II-2a", "IP", []), slot("II-2b", "TRL", ["TRL 4"]), slot("III-1", "시제품", ["3차 시제품"]), slot("III-2", "일정", []), slot("III-3", "애로", []),
                  slot("IV", "팀", []), slot("EN", "영문", [])],
        "ip": {"patents": [{"name": "군집 제어 방법", "filed_no": "10-2024-0012345", "applicant": "KAIST 산학협력단"}], "other": [], "relations": [], "trl": {"level": 4, "evidence": "시험 3회"}},
        "gaps": [{"item": "PM 인적사항", "why_needed": "표지 필수", "slot_ids": ["IV"], "question_to_team": "PM 성명·소속·연락처는?", "priority": "high"}],
        "contact": {"name": "홍길동", "email": "a@b.c"},
    }
    (ws / "02_fact_pack.json").write_text(json.dumps(fp, ensure_ascii=False, indent=2), encoding="utf-8")
    (ws / "01_extract").mkdir(); (ws / "01_extract" / "image_catalog.json").write_text(json.dumps({"images": []}), encoding="utf-8")
    errs = validate.validate_phase(ws, "fact_pack"); print("fact_pack:", errs or "OK")
    ok, reasons = gate.check(ws, "2"); print("gate 2:", ok, reasons)

    sec = lambda sid, title, blocks: {"id": sid, "title": title, "judge_question": "?", "governing": "결론", "page_budget": 0.5, "blocks": blocks}
    cal = {"type": "callout", "text": "농가 방제 시간을 8시간에서 30분으로 줄입니다."}
    figref = {"type": "figure_ref", "figure_id": "fig_kpi", "caption": "[그림 1] 고통의 크기", "source": "출처: 팀 사실 팩", "proves": "→ 증명: 문제 크기"}
    draft = {
        "team": "샘플팀", "edu_type": "해외",
        "cover": {"region": "충청권", "org": "KAIST", "org_type": "대학", "address": "대전", "team_ko": "샘플팀", "team_en": "Sample", "item_ko": "군집 드론 방제", "item_en": "Swarm drone",
                  "tech_field": "IT", "industry": "제조업", "EL": fp["people"]["EL"], "PM": {"name": "[기입 필요: PM]"}, "PI": {"name": "김교수"}},
        "sections": [
            sec("S_I1", "동기", [cal, {"type": "para", "text": "2025.04 텍스코어에 선정되어 농가 120곳을 인터뷰했습니다."}]),
            sec("S_I2", "아이템", [cal, {"type": "heading", "text": "□ 컨셉"}, figref, {"type": "figure_ref", "figure_id": "fig_comp", "caption": "[그림 2] 경쟁표", "source": "s", "proves": "p"},
                                   {"type": "bullets", "items": ["경쟁사 A: 4,800만 원", "시장: 국내 3,240억 원(2025)"]}]),
            sec("S_II1", "기술", [cal, figref, {"type": "para", "text": "특허 10-2024-0012345로 군집 제어를 보호합니다."}]),
            sec("S_II2_PLAN", "확보", [cal, {"type": "para", "text": "KAIST 산학협력단과 기술이전을 협의합니다."}]),
            sec("S_II2_UPGRADE", "업그레이드", [cal, {"type": "para", "text": "[목표] 2027년까지 시험 3회를 통과합니다."}]),
            sec("S_III1", "시제품", [cal, figref, {"type": "table", "caption": "[표 1] 비용", "columns": ["항목", "금액"], "rows": [["재료비", "[기입 필요: 금액]"]]}]),
            sec("S_III2", "일정", [cal, figref]),
            sec("S_III3", "애로", [{"type": "para", "text": "없음"}]),
            sec("S_EN1", "EN", [{"type": "para", "text": "Swarm drone control."}]), sec("S_EN2", "EN", [{"type": "para", "text": "Farmers."}]), sec("S_EN3", "EN", [{"type": "para", "text": "Cheaper than A."}]),
        ],
        "fixed_tables": {"patents": [["군집 제어 방법", "2024", "KR", "10-2024-0012345", "KAIST 산학협력단", "", "", "", ""]], "other_ip": [], "ip_relations": [["특허", "군집 제어 방법", "10-2024-0012345", "KAIST 산학협력단", "홍길동", "발명자는 EL 본인"]],
                         "trl": {"level": 4}, "team_members": [["EL", "홍길동", "1990.01.01", "KAIST", "박사과정", "010-0000-0000", "a@b.c", "본인", "남"]], "team_careers": [["EL", "홍길동", "KAIST", "항공우주", "드론 개발", "총괄"]]},
        "figures": [{"id": "fig_kpi", "type": "kpi_strip", "section_id": "S_I2", "data": {"items": [{"value": "8", "unit": "시간", "label": "방제 시간", "source": "팀"}]}},
                    {"id": "fig_comp", "type": "competitor_matrix", "section_id": "S_I2", "data": {}}],
    }
    (ws / "04_draft_v1.json").write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    errs = validate.validate_phase(ws, "draft"); print("draft:", errs or "OK")
    print("lint:", validate.lint_phase(ws, "draft"))
    rep = trace_numbers.run(ws, ws / "04_draft_v1.json"); print("trace untraced:", rep["untraced"])
    ok, reasons = gate.check(ws, "3"); print("gate 3:", ok, reasons)
    draft["sections"][1]["blocks"].append({"type": "para", "text": "시장은 9,999억 원입니다. 이 제품은 세계 최고 수준입니다."})
    (ws / "04_draft_v1.json").write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    print("draft(bad):", validate.validate_phase(ws, "draft"))
    print("trace(bad):", [u["token"] for u in trace_numbers.run(ws, ws / "04_draft_v1.json")["untraced"]])
    p = build_fillspec.build(ws, ws / "04_draft_v1.json"); spec = json.loads(p.read_text(encoding="utf-8"))
    print("fillspec replacements sample:", {k: v for k, v in spec["replacements"].items() if k.startswith("□") or k in ("{{CV_ORG}}", "{{CV_UNIV}}", "{{EL_NAME}}")})
    print("fillspec sections:", {k: len(v) for k, v in spec["sections"].items()}, "trl:", spec["trl"], "del_en:", spec["delete_english_section"])
    print("WS:", ws)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

def test_sanity():
    assert main() == 0
