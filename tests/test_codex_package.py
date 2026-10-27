# -*- coding: utf-8 -*-
"""Codex 배포판(작업 폴더 ZIP) 빌드 검증."""
import json
import os
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_codex_package as bcp  # noqa: E402

FORBIDDEN = ["BRIAN Dropbox", "Users/pc", "Users\\pc", "에어로봇", "13분과", "회의자료 p.", "사전검토의견서", "1.98", "25팀", "평균 72"]
TEXT_EXT = {".md", ".py", ".json", ".css", ".html", ".txt", ".toml"}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("codex_pkg")
    pkg, zp = bcp.build(out)
    return pkg, zp


def test_package_layout(built):
    pkg, _ = built
    for rel in ["AGENTS.md", "README.md", "NOTICE.md", "사용설명서.html", "VERSION.txt", "FILE-MANIFEST.json", "requirements.txt", "LICENSE",
                ".agents/skills/texcore-plan/SKILL.md", ".agents/skills/texcore-plan/scripts/harness.py",
                ".agents/skills/texcore-plan/scripts/prepare_project.py", ".agents/skills/texcore-plan/scripts/publish_results.py",
                ".agents/skills/texcore-plan/scripts/finish_in_hwp.py", ".agents/skills/texcore-plan/assets/template/template_master.hwpx",
                ".agents/skills/texcore-plan/references/form_map.md", ".agents/skills/texcore-plan/references/judge_calibration.md",
                "docs/beginner-start.md", "docs/advanced-guide.md", "examples/진동지기/진동지기_팀자료_요약.md", "examples/미리보기/example_page_02.png",
                "자료넣는곳/여기에_우리팀_자료를_넣으세요.txt", "결과물/결과는_여기에_생깁니다.txt"]:
        assert (pkg / rel).exists(), rel
    ver = (pkg / "VERSION.txt").read_text(encoding="utf-8").strip()
    assert ver == bcp.version()
    for name in ("README.md", "사용설명서.html", "docs/beginner-start.md"):
        t = (pkg / name).read_text(encoding="utf-8")
        assert "{VERSION}" not in t and ver in t, name


def test_codex_skill_is_codex_version(built):
    pkg, _ = built
    t = (pkg / ".agents/skills/texcore-plan/SKILL.md").read_text(encoding="utf-8")
    assert t.startswith("---\nname: texcore-plan\n")
    for k in ["prepare_project.py", "publish_results.py", "finish_in_hwp.py", "spawn", "tp_intake", "tp_panel", "PERSONA=chair",
              "gate 5", "--accept-risk", "FILL=skip", "work/setup/runtime.json", "결과물/결과보기.html"]:
        assert k in t, k
    assert "Agent(tp-" not in t  # Claude Code 전용 호출 표기가 남아 있으면 안 된다


def test_agent_tomls(built):
    pkg, _ = built
    tomls = sorted((pkg / ".codex/agents").glob("*.toml"))
    assert [p.stem for p in tomls] == ["tp_designer", "tp_finalizer", "tp_intake", "tp_panel", "tp_researcher", "tp_writer"]
    for p in tomls:
        d = tomllib.loads(p.read_text(encoding="utf-8"))
        assert set(d) >= {"name", "description", "developer_instructions"}, p.name
        assert d["name"] == p.stem and len(d["description"]) > 30
        di = d["developer_instructions"]
        assert "WS=" in di and "SKILL_DIR=" in di and p.stem in di and len(di) > 800, p.name
        assert "model" not in d


def test_manifest_and_zip(built):
    pkg, zp = built
    man = json.loads((pkg / "FILE-MANIFEST.json").read_text(encoding="utf-8"))
    files = {f"{bcp.PKG_NAME}/{f.relative_to(pkg).as_posix()}" for f in pkg.rglob("*") if f.is_file()} - {f"{bcp.PKG_NAME}/FILE-MANIFEST.json"}
    assert set(man) == files
    for rel, h in list(man.items())[:20]:
        assert bcp.sha256(pkg / Path(rel).relative_to(bcp.PKG_NAME)) == h
    with zipfile.ZipFile(zp) as z:
        assert z.testzip() is None
        names = z.namelist()
        assert f"{bcp.PKG_NAME}/AGENTS.md" in names and f"{bcp.PKG_NAME}/.codex/agents/tp_intake.toml" in names
        assert all(n.startswith(bcp.PKG_NAME + "/") for n in names)
    assert zp.stat().st_size < 30 * 1024 * 1024


def test_no_private_strings_in_package(built):
    pkg, _ = built
    hits = []
    for f in pkg.rglob("*"):
        if f.is_file() and f.suffix.lower() in TEXT_EXT:
            t = f.read_text(encoding="utf-8", errors="ignore")
            hits += [f"{f.relative_to(pkg)}: {s}" for s in FORBIDDEN if s in t]
    assert not hits, "\n".join(hits)


def test_prepare_project_writes_runtime(built, tmp_path):
    pkg, _ = built
    proj = tmp_path / "proj"
    import shutil
    shutil.copytree(pkg, proj)
    r = subprocess.run([sys.executable, "-X", "utf8", str(proj / ".agents/skills/texcore-plan/scripts/prepare_project.py"), "--project", str(proj), "--team", "테스트팀"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    rt = json.loads((proj / "work/setup/runtime.json").read_text(encoding="utf-8"))
    assert rt["schema_version"].startswith("texcore-plan-preparation") and rt["python"] and "hwp" in rt and "chrome" in rt
    assert (proj / "project.json").exists() and (proj / "자료넣는곳").is_dir() and (proj / "결과물").is_dir()
    cfg = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    assert cfg["team_name"] == "테스트팀" and cfg["input_dir"] == "자료넣는곳" and cfg["work_dir"] == "work"
    assert r.returncode in (0, 2), r.stdout + r.stderr  # 2 = 패키지 미설치(설치 생략)


def test_publish_results_on_minimal_workspace(built, tmp_path):
    pkg, _ = built
    import shutil
    proj = tmp_path / "proj2"; shutil.copytree(pkg, proj)
    sys.path.insert(0, str(proj / ".agents/skills/texcore-plan/scripts"))
    from state import State  # 패키지 안 하네스 모듈
    ws = proj / "work" / "2026.10.28_테스트팀_TexcorePlan"; ws.mkdir(parents=True)
    State.new(ws, team="테스트팀", input_dir=str(proj / "자료넣는곳"), edu_type="해외")
    draft = {"cover": {"team_ko": "테스트팀", "org": "한빛대학교"}, "sections": [
        {"id": "S_I1", "title": "Ⅰ-1. 추진 동기와 목표", "governing": "결론 한 문장", "blocks": [
            {"type": "callout", "text": "현장 인터뷰 32건으로 확인한 문제를 검증합니다."}, {"type": "subheading", "text": "지원 동기"},
            {"type": "para", "text": "본문 문단."}, {"type": "bullets", "items": ["항목 1", "항목 2"]},
            {"type": "table", "caption": "[표 1] 예시", "columns": ["구분", "값"], "rows": [["a", "1"], ["b", "2"]]},
            {"type": "figure_ref", "figure_id": "fig_kpi", "caption": "[그림 1] 예시", "proves": "증명", "source": "출처"}]}],
        "fixed_tables": {"patents": [["특허명", "2024", "KR", "10-2024-0000001", "출원인", "", "", "", ""]], "trl": {"level": 4}},
        "to_secure": ["PM 인적사항"]}
    (ws / "07_draft_v2.json").write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    (ws / "08_fill_spec.json").write_text("{}", encoding="utf-8")
    (ws / "08_figures").mkdir(); (ws / "08_figures" / "fig_kpi.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (ws / "02_team_questions.md").write_text("# 질문", encoding="utf-8")
    r = subprocess.run([sys.executable, "-X", "utf8", str(proj / ".agents/skills/texcore-plan/scripts/publish_results.py"), "--project", str(proj), "--ws", str(ws)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    root_html = proj / "결과물" / "결과보기.html"
    assert root_html.exists() and "한글 주입 전" in root_html.read_text(encoding="utf-8")
    dest = next(d for d in (proj / "결과물").iterdir() if d.is_dir())
    md = (dest / "신청서_본문초안.md").read_text(encoding="utf-8")
    assert "Ⅰ-1. 추진 동기와 목표" in md and "| 구분 | 값 |" in md and "[그림 1] 예시" in md and "10-2024-0000001" in md
    assert (dest / "도식" / "fig_kpi.png").exists() and (dest / "팀_질문지.md").exists() and (dest / "주입사양.json").exists()
