#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한글이 있는 Windows에서 마지막 단계(한글 주입 → 쪽 검수 → 최종 복사 → 게시)를 한 번에 실행한다.

사용(PowerShell, 프로젝트 폴더에서):
  python .agents\\skills\\texcore-plan\\scripts\\finish_in_hwp.py --project . [--ws <워크스페이스>]

Mac이나 한글이 없는 PC에서 1~5단계(도식·주입 사양)까지 끝낸 프로젝트 폴더를 그대로 가져와 실행하면 된다.
Codex 안에서 한글 COM 실행이 막힐 때 Codex가 이 명령을 안내한다.
"""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _run(args: list[str]) -> int:
    print("$", " ".join(args)); return subprocess.call(args)


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=Path, default=Path("."))
    ap.add_argument("--ws", type=Path)
    a = ap.parse_args(argv)
    if sys.platform != "win32":
        print("이 단계는 Windows + 한글(HWP)에서만 실행됩니다."); return 2
    sys.path.insert(0, str(HERE))
    import publish_results  # noqa: E402
    project = a.project.resolve()
    ws = a.ws.resolve() if a.ws else publish_results.latest_ws(project, "work")
    if ws is None:
        print("워크스페이스(work/*_TexcorePlan)를 찾지 못했습니다."); return 2
    if not (ws / "08_fill_spec.json").is_file():
        print(f"08_fill_spec.json이 없습니다({ws}). 5단계(도식·주입 사양)까지 먼저 진행하세요."); return 2
    py = sys.executable; h = str(HERE / "harness.py")
    for cmd in (["fill"], ["qa"], ["gate", "6"], ["final"], ["gate", "final"]):
        rc = _run([py, "-X", "utf8", h, *cmd, "--ws", str(ws)])
        if rc != 0 and cmd[0] not in ("gate",):
            print(f"[중단] {cmd[0]} 단계 실패(코드 {rc}). 한글 창이 떠 있으면 닫고, `harness.py` 메시지를 Codex에게 전달하세요."); return rc
    publish_results.publish(project, ws)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
