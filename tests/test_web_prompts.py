# -*- coding: utf-8 -*-
"""Gemini·ChatGPT 웹용 프롬프트 북(web/*.md → docs/web.html) 검증."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_web_prompts as bwp  # noqa: E402

SRC = ROOT / "web" / "텍스코어_신청서_프롬프트북.md"
FORBIDDEN = ["BRIAN Dropbox", "Users/pc", "에어로봇", "13분과", "회의자료", "사전검토의견서", "1.98", "25팀", "평균 72"]


def _prompts(md: str) -> list[str]:
    return re.findall(r"```prompt\n(.*?)\n```", md, re.S)


def test_markdown_structure():
    md = SRC.read_text(encoding="utf-8")
    assert md.startswith("# 텍스코어 사업신청서 프롬프트 북")
    heads = re.findall(r"^## (.+)$", md, re.M)
    for k in ["0. 시작 전에", "1단계", "2단계", "3단계", "4단계", "5단계", "6단계", "7단계", "8단계", "9단계", "10.", "부록 A", "부록 B", "부록 C"]:
        assert any(h.startswith(k) for h in heads), k
    ps = _prompts(md)
    assert 9 <= len(ps) <= 16, len(ps)
    for p in ps:
        assert 600 <= len(p) <= 3600, (len(p), p[:60])
    # 단계 1~9 마다 프롬프트가 최소 1개
    for n in range(1, 10):
        sec = md.split(f"## {n}단계")[1].split("\n## ")[0]
        assert "```prompt" in sec, f"{n}단계 프롬프트 없음"


def test_prompts_contain_safety_devices():
    md = SRC.read_text(encoding="utf-8")
    assert "[기입 필요]" in md and "[확보 필요]" in md and "80자" in md and "결론" in md
    joined = "\n".join(_prompts(md))
    for k in ["[기입 필요]", "출처", "vc", "layman", "80점", "캡션", "→ 증명"]:
        assert k in joined, k
    assert "{팀명}" in joined


def test_no_private_strings():
    t = SRC.read_text(encoding="utf-8")
    hits = [s for s in FORBIDDEN if s in t]
    assert not hits, hits


def test_html_build(tmp_path):
    out = tmp_path / "web.html"
    r = bwp.build(SRC, out)
    t = out.read_text(encoding="utf-8")
    assert r["prompts"] >= 9 and r["sections"] >= 13
    assert t.count('class="prompt"') == r["prompts"] and "copyPrompt" in t
    assert "<script src=" not in t and 'href="index.html"' in t
    assert "#FF385C" in t.upper()


def test_committed_html_is_up_to_date(tmp_path):
    """docs/web.html은 build_web_prompts.py로 다시 만든 결과와 같아야 한다."""
    out = tmp_path / "web.html"
    bwp.build(SRC, out)
    assert (ROOT / "docs" / "web.html").read_text(encoding="utf-8") == out.read_text(encoding="utf-8")
