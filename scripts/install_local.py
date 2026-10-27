# -*- coding: utf-8 -*-
"""저장소 → 로컬 .claude 설치본 동기화 (+ 비공개 참조 오버레이).

사용:
  python scripts/install_local.py                      # 상위로 올라가며 처음 만나는 .claude 에 설치
  python scripts/install_local.py --target "<.claude 폴더>"
  python scripts/install_local.py --private "<폴더>"   # 오버레이 폴더 지정(기본: 저장소 옆 ../_private/references)
  python scripts/install_local.py --no-private         # 공개판 그대로 설치

동작:
  plugins/texcore-plan/skills/texcore-plan → <target>/skills/texcore-plan   (기존 폴더 삭제 후 복사)
  plugins/texcore-plan/agents/tp-*.md      → <target>/agents/
  <private>/*.md                           → <target>/skills/texcore-plan/references/  (같은 파일명 덮어쓰기)
비공개 오버레이는 git 밖(저장소 상위 `_private/references/`)에 두는 심사위원 내부 캘리브레이션 자료다.
"""
from __future__ import annotations
import argparse, shutil, sys, time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
SKILL_SRC = ROOT / "plugins" / "texcore-plan" / "skills" / "texcore-plan"
AGENTS_SRC = ROOT / "plugins" / "texcore-plan" / "agents"
DEFAULT_PRIVATE = ROOT.parent / "_private" / "references"


def find_claude_dir(start: Path) -> Path | None:
    for p in [start, *start.parents]:
        c = p / ".claude"
        if (c / "skills").is_dir():
            return c
    return None


def rmtree_retry(p: Path, tries: int = 5) -> None:
    """Dropbox 동기화가 파일을 잠가 WinError 32가 나는 경우를 견딘다."""
    for _ in range(tries):
        shutil.rmtree(p, ignore_errors=True)
        if not p.exists():
            return
        time.sleep(0.5)
    if p.exists():
        raise RuntimeError(f"삭제 실패(잠김?): {p}")


def copy_tree(src: Path, dst: Path) -> int:
    rmtree_retry(dst)
    n = 0
    for f in src.rglob("*"):
        if f.is_dir() or "__pycache__" in f.parts or f.name.startswith(("~$", ".")):
            continue
        out = dst / f.relative_to(src)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out); n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", help=".claude 폴더(기본: 상위에서 탐색)")
    ap.add_argument("--private", help="비공개 참조 오버레이 폴더(기본: ../_private/references)")
    ap.add_argument("--no-private", action="store_true", help="오버레이 없이 공개판 그대로 설치")
    a = ap.parse_args()

    target = Path(a.target).resolve() if a.target else find_claude_dir(ROOT)
    if not target:
        print("[오류] .claude 폴더를 찾지 못했습니다. --target으로 지정하세요."); return 1
    if not SKILL_SRC.exists():
        print(f"[오류] 스킬 원본이 없습니다: {SKILL_SRC}"); return 1

    skill_dst = target / "skills" / "texcore-plan"
    n1 = copy_tree(SKILL_SRC, skill_dst)
    (target / "agents").mkdir(parents=True, exist_ok=True)
    n2 = 0
    for f in sorted(AGENTS_SRC.glob("tp-*.md")):
        shutil.copy2(f, target / "agents" / f.name); n2 += 1

    overlaid: list[str] = []
    if not a.no_private:
        priv = Path(a.private).resolve() if a.private else DEFAULT_PRIVATE
        if priv.is_dir():
            for f in sorted(priv.glob("*.md")):
                shutil.copy2(f, skill_dst / "references" / f.name); overlaid.append(f.name)
        elif a.private:
            print(f"[경고] 오버레이 폴더가 없습니다: {priv}")

    print(f"설치 완료 → {target}")
    print(f"  skills/texcore-plan: {n1}개 파일")
    print(f"  agents/tp-*.md: {n2}개")
    print(f"  비공개 오버레이: {', '.join(overlaid) if overlaid else '없음(공개판)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
