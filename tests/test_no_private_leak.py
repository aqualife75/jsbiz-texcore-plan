# -*- coding: utf-8 -*-
"""공개 저장소에 들어가면 안 되는 것 — 개인 경로, 실제 팀 자료, 심사위원 내부 자료 흔적."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_EXT = {".md", ".py", ".json", ".css", ".html", ".txt", ".ini", ".toml"}
FORBIDDEN = [
    "BRIAN Dropbox", "Users/pc", "Users\\pc", "Users/leedg", "D:/Dropbox", "D:\\Dropbox",   # 개인 경로
    "에어로봇", "realrun_",                                                              # 실전 테스트 팀 자료
    "13분과", "평가결과_13분과", "회의자료 p.", "작성안내 '", "사전검토의견 작성안내",      # 심사위원 내부 자료
    "2026.03.26_텍스코어 심사",
    "1.98", "25팀", "평균 72", "89점", "후보 70", "탈락 70", "사전검토의견서",                   # 내부 통계·규칙
]


def _files():
    for p in ROOT.rglob("*"):
        if p.is_dir() or p.suffix.lower() not in TEXT_EXT:
            continue
        if any(part in {".git", "__pycache__", "_out", ".pytest_cache"} for part in p.parts):
            continue
        if p.parent.name == "tests" and p.name.startswith("test_"):
            continue  # 테스트 파일 자신이 금지어를 담는다
        yield p


def test_no_private_strings_in_repo():
    hits = []
    for p in _files():
        t = p.read_text(encoding="utf-8", errors="ignore")
        for s in FORBIDDEN:
            if s in t:
                hits.append(f"{p.relative_to(ROOT)}: {s}")
    assert not hits, "\n".join(hits)
