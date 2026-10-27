#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""교육생 프로젝트 실행 환경 준비(표준 라이브러리만). 신청서를 작성하지는 않는다.

사용: <python> .agents/skills/texcore-plan/scripts/prepare_project.py --project . [--team 팀명] [--install-missing]

하는 일
- project.json(없으면 생성: team_name·input_dir·work_dir), 자료넣는곳/·결과물/·work/setup/ 폴더
- 현재 Python 또는 프로젝트 전용 .venv에서 필요한 모듈(pymupdf·pillow·olefile·python-docx·openpyxl·python-pptx·jsonschema·lxml,
  Windows는 pywin32) 확인. --install-missing이면 .venv를 만들고 requirements.txt로 설치(사용자 전역 환경은 건드리지 않음)
- Chrome/Edge(도식 렌더·근거 캡처), 한글(HWP) COM 등록 여부(Windows) 확인
- work/setup/runtime.json에 결과 기록: python·ready·hwp·chrome·needs·retry_request
"""
from __future__ import annotations
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
MIN_PYTHON = (3, 10)
REQUIRED = {"fitz": "pymupdf", "PIL": "pillow", "olefile": "olefile", "docx": "python-docx", "openpyxl": "openpyxl",
            "pptx": "python-pptx", "jsonschema": "jsonschema", "lxml": "lxml"}
WINDOWS_REQUIRED = {"win32com": "pywin32"}
PROBE_PREFIX = "TEXCORE_PROBE:"
PROBE = r'''
import importlib, json, sys
names = %s
checks = {}
for n in names:
    try:
        m = importlib.import_module(n); checks[n] = {"ok": True, "version": str(getattr(m, "__version__", getattr(m, "VersionBind", "")))}
    except Exception as e:
        checks[n] = {"ok": False, "error": type(e).__name__}
print("TEXCORE_PROBE:" + json.dumps({"version": list(sys.version_info[:3]), "prefix": sys.prefix, "executable": sys.executable, "modules": checks}))
'''


class SetupError(ValueError):
    """교육생에게 보여도 되는 짧은 메시지. 원인은 로그에."""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class Log:
    def __init__(self, path: Path):
        self.path = path

    def __call__(self, phase: str, **d):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": _utc(), "phase": phase, **d}, ensure_ascii=False, default=str) + "\n")


def run(cmd: list[str], log: Log, phase: str, timeout: int, cwd: Path | None = None) -> dict:
    t0 = time.monotonic(); r = {"ok": False, "returncode": None, "stdout": "", "stderr": ""}
    try:
        c = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        r.update(ok=c.returncode == 0, returncode=c.returncode, stdout=c.stdout, stderr=c.stderr)
    except subprocess.TimeoutExpired as e:
        r.update(reason="timeout", stdout=e.stdout or "", stderr=e.stderr or "")
    except OSError as e:
        r.update(reason="start_failed", stderr=str(e))
    r["elapsed"] = round(time.monotonic() - t0, 2)
    log(phase, command=cmd, ok=r["ok"], returncode=r["returncode"], stderr=r["stderr"][-800:], elapsed=r["elapsed"])
    return r


def required_names() -> dict:
    names = dict(REQUIRED)
    if os.name == "nt":
        names.update(WINDOWS_REQUIRED)
    return names


def probe_python(exe: str | Path, log: Log) -> dict:
    names = list(required_names())
    r = run([str(exe), "-I", "-c", PROBE % json.dumps(names)], log, "python_probe", 60)
    rep = {"executable": str(exe), "version": [], "modules": {}, "ok": r["ok"]}
    for line in reversed(r.get("stdout", "").splitlines()):
        if line.startswith(PROBE_PREFIX):
            try:
                rep.update(json.loads(line[len(PROBE_PREFIX):]))
            except ValueError:
                pass
            break
    rep["missing"] = [n for n in names if not rep.get("modules", {}).get(n, {}).get("ok")]
    rep["supported"] = tuple(rep.get("version", [0, 0])[:2]) >= MIN_PYTHON
    rep["ready"] = bool(rep["supported"] and not rep["missing"] and r["ok"])
    return rep


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def find_chrome() -> str | None:
    cands: list[str] = []
    if os.name == "nt":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files"); pfx = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        loc = os.environ.get("LOCALAPPDATA", "")
        cands += [rf"{pf}\Google\Chrome\Application\chrome.exe", rf"{pfx}\Google\Chrome\Application\chrome.exe",
                  rf"{loc}\Google\Chrome\Application\chrome.exe", rf"{pfx}\Microsoft\Edge\Application\msedge.exe",
                  rf"{pf}\Microsoft\Edge\Application\msedge.exe"]
    elif sys.platform == "darwin":
        cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "chrome", "msedge"):
        w = shutil.which(n)
        if w:
            cands.append(w)
    for c in cands:
        if c and Path(c).is_file():
            return c
    return None


def hwp_status(py_report: dict) -> dict:
    if os.name != "nt":
        return {"available": False, "reason": "Windows가 아님 — 한글 주입(5단계)은 Windows + 한글(HWP)에서만 가능"}
    registered = False
    try:
        import winreg  # type: ignore
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"HWPFrame.HwpObject"):
            registered = True
    except OSError:
        registered = False
    pywin = py_report.get("modules", {}).get("win32com", {}).get("ok", False)
    if registered and pywin:
        return {"available": True, "reason": "한글 COM 등록 + pywin32 확인"}
    if not registered:
        return {"available": False, "reason": "한글(HWP)이 설치되어 있지 않거나 COM 등록이 없음(HWPFrame.HwpObject)"}
    return {"available": False, "reason": "pywin32 모듈 없음 — 준비 스크립트가 설치하거나 pip install pywin32"}


def ensure_project(project: Path, team: str) -> dict:
    cfg_p = project / "project.json"
    if cfg_p.exists():
        cfg = json.loads(cfg_p.read_text(encoding="utf-8-sig"))
        if not isinstance(cfg, dict):
            raise SetupError("기존 project.json 형식을 확인해야 합니다. 덮어쓰지 않았습니다.")
        status = "resumed"
    else:
        cfg = {"schema_version": "texcore-plan-project.v1", "team_name": team.strip() or "우리팀", "input_dir": "자료넣는곳",
               "work_dir": "work", "edu_type": None, "created_at": _utc(), "data_policy": "one-team-per-project"}
        cfg_p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        status = "initialized"
    for rel in (cfg.get("input_dir", "자료넣는곳"), "결과물", cfg.get("work_dir", "work"), "work/setup"):
        (project / rel).mkdir(parents=True, exist_ok=True)
    return {"config": cfg, "status": status}


def prepare(project: Path, team: str, install_missing: bool) -> dict:
    project = Path(project).resolve()
    if not project.is_dir():
        raise SetupError("프로젝트 폴더를 찾지 못했습니다.")
    info = ensure_project(project, team)
    cfg = info["config"]
    setup = project / "work" / "setup"; setup.mkdir(parents=True, exist_ok=True)
    log = Log(setup / f"setup-{datetime.now():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}.log")
    checks: dict = {}; needs: list[dict] = []

    current = probe_python(sys.executable, log); checks["current_python"] = current
    selected, selected_exe = current, Path(sys.executable)
    venv = project / ".venv"; vexe = venv_python(venv)
    if vexe.is_file():
        existing = probe_python(vexe, log); checks["existing_venv"] = existing
        if existing["ready"]:
            selected, selected_exe = existing, vexe
    if not selected["ready"] and install_missing:
        try:
            if not current["supported"]:
                raise SetupError("Python 3.10 이상이 필요합니다. Codex가 사용 가능한 Python을 찾아야 합니다.")
            if not vexe.is_file():
                c = run([sys.executable, "-I", "-m", "venv", "--copies", str(venv)], log, "venv_create", 240, project)
                checks["venv_creation"] = {"ok": c["ok"], "returncode": c["returncode"]}
                if not c["ok"]:
                    raise SetupError("프로젝트 전용 실행 환경(.venv)을 만들지 못했습니다. Codex가 준비 로그를 확인해야 합니다.")
            req = next((p for p in (project / "requirements.txt", SKILL_DIR / "requirements.txt") if p.is_file()), None)
            if req is None:
                raise SetupError("requirements.txt를 찾지 못했습니다. 배포본 구성을 확인해야 합니다.")
            c = run([str(vexe), "-I", "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--timeout", "30", "-r", str(req)],
                    log, "pip_install", 600, project)
            checks["installation"] = {"ok": c["ok"], "returncode": c["returncode"], "requirements": str(req)}
            if not c["ok"]:
                needs.append({"kind": "package_installation", "message": "패키지 설치에 실패했습니다. 인터넷 연결과 준비 로그를 확인한 뒤 다시 시도해야 합니다."})
            selected = probe_python(vexe, log); selected_exe = vexe
        except SetupError as e:
            log("preparation_action_needed", message=str(e)); needs.append({"kind": "python_environment", "message": str(e)})
    if not selected["ready"]:
        needs.append({"kind": "python_packages", "modules": selected.get("missing", []),
                      "message": ("필요한 Python 패키지가 없습니다: " + ", ".join(required_names()[m] for m in selected.get("missing", [])) + " — --install-missing으로 준비합니다.")
                      if selected.get("supported") else "Python 3.10 이상이 필요합니다."})
    checks["selected_python"] = {k: v for k, v in selected.items() if k != "modules"} | {"modules": selected.get("modules", {})}

    chrome = find_chrome(); checks["chrome"] = chrome
    if not chrome:
        needs.append({"kind": "chrome", "message": "Chrome 또는 Edge가 없어 증거 도식 렌더·근거 캡처를 할 수 없습니다. 둘 중 하나를 설치해야 합니다."})
    hwp = hwp_status(selected); checks["hwp"] = hwp

    ready = bool(selected["ready"] and chrome)
    report = {"schema_version": "texcore-plan-preparation.v1", "prepared_at": _utc(), "team_name": cfg.get("team_name", team),
              "project_status": info["status"], "python": str(selected_exe), "ready": ready, "os": platform.platform(),
              "hwp": hwp, "chrome": chrome, "input_dir": cfg.get("input_dir", "자료넣는곳"), "work_dir": cfg.get("work_dir", "work"),
              "scope": "실행 환경 준비; 자료 분석과 신청서 작성은 다음 단계입니다.", "checks": checks, "needs": needs,
              "log": log.path.relative_to(project).as_posix(), "retry_request": "환경 준비를 다시 확인해줘."}
    (setup / "runtime.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return report


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="Codex가 프로젝트 실행 환경을 준비합니다. 신청서는 작성하지 않습니다.")
    ap.add_argument("--project", type=Path, default=Path("."))
    ap.add_argument("--team", default="우리팀")
    ap.add_argument("--install-missing", action="store_true")
    a = ap.parse_args(argv)
    try:
        rep = prepare(a.project, a.team, a.install_missing)
    except SetupError as e:
        print(str(e)); print("Codex에게 \"환경 준비를 다시 확인해줘\"라고 말씀해 주세요."); return 2
    except Exception as e:  # noqa: BLE001
        print(f"환경 준비를 마치지 못했습니다({type(e).__name__}). Codex가 work/setup 로그를 확인해야 합니다."); return 2
    print(f"python: {rep['python']}")
    print(f"한글 주입(5단계): {'가능' if rep['hwp']['available'] else '불가 — ' + rep['hwp']['reason']}")
    print(f"Chrome/Edge: {rep['chrome'] or '없음'}")
    if rep["ready"]:
        print("실행 환경 준비가 끝났습니다. 자료 분석과 신청서 작성은 아직 시작하지 않았습니다."); return 0
    print("준비가 아직 끝나지 않았습니다. " + rep["needs"][0]["message"])
    print("Codex에게 \"환경 준비를 다시 확인해줘\"라고 말씀해 주세요."); return 2


if __name__ == "__main__":
    raise SystemExit(main())
