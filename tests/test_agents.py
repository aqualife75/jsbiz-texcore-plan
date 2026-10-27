# -*- coding: utf-8 -*-
import re
from pathlib import Path

AG = Path(__file__).resolve().parents[1] / "plugins/texcore-plan/agents"
NAMES = ["tp-intake", "tp-writer", "tp-panel", "tp-researcher", "tp-designer", "tp-finalizer"]


def _front(name):
    t = (AG / f"{name}.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", t, re.S)
    assert m, name
    return m.group(1), m.group(2)


def test_agents_exist_with_frontmatter_and_no_model():
    for n in NAMES:
        fm, body = _front(n)
        assert f"name: {n}" in fm and "description:" in fm and "tools:" in fm, n
        assert not re.search(r"^model:", fm, re.M), f"{n}: model 필드 금지(서브에이전트 모델 정책)"
        assert "WS=" in body and "SKILL_DIR=" in body and "PY=" in body, n


def test_tool_sets():
    assert "WebSearch" in _front("tp-researcher")[0] and "WebFetch" in _front("tp-researcher")[0]
    assert "WebSearch" not in _front("tp-writer")[0]
    assert "Bash" in _front("tp-designer")[0]


def test_no_fabrication_rule_present():
    for n in NAMES:
        body = _front(n)[1]
        assert ("없는 숫자" in body) or ("숫자를 만들" in body) or ("창작" in body) or ("지어내" in body), n
