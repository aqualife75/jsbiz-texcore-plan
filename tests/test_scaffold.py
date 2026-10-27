# -*- coding: utf-8 -*-
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_marketplace_manifest():
    m = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert m["name"] == "jsbiz-texcore-plan"
    assert m["plugins"][0]["name"] == "texcore-plan"
    assert m["plugins"][0]["source"] == "./plugins/texcore-plan"


def test_plugin_manifest():
    p = json.loads((ROOT / "plugins/texcore-plan/.claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert p["name"] == "texcore-plan"
    assert p["version"].count(".") == 2


def test_requirements_lists_core_libs():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for lib in ["python-pptx", "pymupdf", "pillow", "olefile", "python-docx", "openpyxl", "jsonschema", "lxml", "pywin32"]:
        assert lib in req, lib


def test_template_assets_present():
    t = ROOT / "plugins/texcore-plan/skills/texcore-plan/assets/template"
    assert (t / "template_master.hwpx").exists() and (t / "anchors.json").exists()
    a = json.loads((t / "anchors.json").read_text(encoding="utf-8"))
    assert len(a.get("anchors", [])) >= 50


def test_private_overlay_dir_is_outside_repo():
    """비공개 참조(_private)는 저장소 밖에만 있어야 한다."""
    assert not (ROOT / "_private").exists()
    assert not list(ROOT.rglob("realrun_*"))
