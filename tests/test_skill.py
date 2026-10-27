# -*- coding: utf-8 -*-
import re
from pathlib import Path

S = Path(__file__).resolve().parents[1] / "plugins/texcore-plan/skills/texcore-plan/SKILL.md"


def test_skill_frontmatter_and_phases():
    t = S.read_text(encoding="utf-8")
    assert t.startswith("---\nname: texcore-plan\n") and "description:" in t
    for k in ["HARNESS init", "HARNESS extract --ws", "gate 2", "gate 3", "gate 4", "gate 5", "gate 6", "gate final",
              "tp-intake", "tp-writer", "tp-panel", "tp-researcher", "tp-designer", "tp-finalizer",
              "PERSONA=chair", "MODE=merge", "MODE=outline", "MODE=shrink", "--accept-risk", "--resume", "--type",
              "WS=", "SKILL_DIR=", "PY=", "scripts/harness.py", "팀_확인사항.md", "심사대비_패키지.md"]:
        assert k in t, k
    assert "model" not in re.match(r"^---\n(.*?)\n---", t, re.S).group(1)
