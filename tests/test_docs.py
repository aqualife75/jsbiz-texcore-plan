# -*- coding: utf-8 -*-
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_index_html_sections_and_install():
    t = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    for sid in ["outputs", "prereq", "install", "folder", "run", "check", "revise", "principle", "faq", "disclaimer"]:
        assert f'id="{sid}"' in t, sid
    assert "/plugin marketplace add aqualife75/jsbiz-texcore-plan" in t
    assert "/plugin install texcore-plan@jsbiz-texcore-plan" in t
    assert "Pretendard" in t and "#ff385c" in t.lower()
    assert "<script src=" not in t  # 외부 JS 없음(인라인만)
    for img in ["img/example_page_02.png", "img/example_page_03.png", "img/example_fig_competitor.png", "img/example_fig_gantt.png"]:
        assert img in t and (ROOT / "docs" / img).exists(), img


def test_readme_links():
    t = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "aqualife75.github.io/jsbiz-texcore-plan" in t and "@정석Biz" in t and "texcore-plan@jsbiz-texcore-plan" in t
    assert "팀_확인사항.md" in t and "심사대비_패키지.md" in t
