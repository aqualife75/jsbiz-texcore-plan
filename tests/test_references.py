# -*- coding: utf-8 -*-
import json
from pathlib import Path

SK = Path(__file__).resolve().parents[1] / "plugins/texcore-plan/skills/texcore-plan"
R = SK / "references"
FILES = ["form_map", "section_guides", "writing_rules", "plain_language", "visual_rules", "figure_types",
         "review_rubric", "evidence_policy", "qa_checklist", "judge_calibration", "judge_questions_texcore", "evaluation_guide"]


def test_all_reference_files_exist_with_title():
    for f in FILES:
        p = R / f"{f}.md"
        assert p.exists(), f
        assert p.read_text(encoding="utf-8").lstrip().startswith("# "), f


def test_form_map_has_scores_and_sections():
    t = (R / "form_map.md").read_text(encoding="utf-8")
    for k in ["20", "15", "25", "S_I1", "S_I2", "S_II1", "S_III1", "S_III2", "S_EN1"]:
        assert k in t, k


def test_rubric_has_personas_and_severity():
    t = (R / "review_rubric.md").read_text(encoding="utf-8")
    for k in ["vc", "tlo", "domain", "icorps", "layman", "numbers", "chair", "critical", "major", "minor"]:
        assert k in t, k


def test_figure_types_match_validate():
    import validate  # conftest가 scripts를 sys.path에 넣는다
    t = (R / "figure_types.md").read_text(encoding="utf-8")
    for ft in validate.FIGURE_TYPES:
        assert f"`{ft}`" in t or ft in t, ft


def test_limits_and_banned_phrases_load():
    lim = json.loads((SK / "assets" / "limits.json").read_text(encoding="utf-8"))
    assert lim["page_total_max"] == 10 and "evidence_figures_min" in lim
    bp = json.loads((SK / "assets" / "banned_phrases.json").read_text(encoding="utf-8"))
    assert bp.get("banned") and bp.get("warn")
