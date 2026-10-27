# -*- coding: utf-8 -*-
"""texcore-plan 하네스 CLI. 결정적 작업(추출·검증·추적·게이트·그림 렌더·주입·QA·최종 복사)만 담당한다. 내용 판단은 에이전트가 한다.

사용:
  python harness.py init <입력폴더> [--team 팀명] [--out 폴더] [--type 해외|국내]
  python harness.py extract  --ws <WS>
  python harness.py status   --ws <WS>
  python harness.py validate <target> --ws <WS> [--file 경로]     target: fact_pack|image_catalog|outline|draft|draft_v2|review|evidence|ledger
  python harness.py trace    --ws <WS> [--file 경로]
  python harness.py gate     <2|3|4|5|6|final> --ws <WS> [--accept-risk]
  python harness.py figures  --ws <WS> [--file 초안]               초안 figures[] → 08_figures/*.png
  python harness.py fillspec --ws <WS> [--file 초안] [--remove-page-breaks]  → 08_fill_spec.json (옵션은 08_fill_options.json에 유지)
  python harness.py fill     --ws <WS> [--spec 경로]                → 09_build/{팀}_사업신청서_v1.hwpx + pdf
  python harness.py qa       --ws <WS> [--src hwpx]                 → 09_build/qa/page-NN.png + qa_report.md
  python harness.py final    --ws <WS>                              → 10_final/ 복사·개명
"""
from __future__ import annotations
import argparse, json, re, shutil, sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import extractors  # noqa: E402
import validate  # noqa: E402
import trace_numbers  # noqa: E402
import gate  # noqa: E402
import build_fillspec  # noqa: E402
from state import State, PHASES  # noqa: E402

MASTER = HERE.parent / "assets" / "template" / "template_master.hwpx"
_TEAM_RE = re.compile(r"_\(?([^_()]+?)\)?_[^_]+_사업신청서")  # (권역)_(혁신단)_(기관)_(분야)_(탐색팀)_(EL)_사업신청서 규칙

class WorkspaceError(Exception):
    pass

def infer_team(input_dir: Path) -> str:
    for f in sorted(Path(input_dir).iterdir()):
        m = _TEAM_RE.search(f.name)
        if m and "탐색팀" not in m.group(1): return m.group(1).strip()
    return Path(input_dir).name.strip()

def _ws_from_args(args) -> Path:
    ws = Path(args.ws).resolve()
    if not (ws / "state.json").exists():
        raise WorkspaceError(f"워크스페이스가 아닙니다: {ws}")
    return ws

def _log(ws: Path, line: str) -> None:
    with (ws / "run_log.md").open("a", encoding="utf-8") as f:
        f.write(f"- {datetime.now():%Y-%m-%d %H:%M} {line}\n")

# ───────────────────────── 0. INTAKE ─────────────────────────
def cmd_init(args) -> int:
    src = Path(args.input_dir).resolve()
    if not src.is_dir():
        print(f"[오류] 입력 폴더 없음: {src}"); return 1
    team = args.team or infer_team(src)
    out_root = Path(args.out).resolve() if args.out else src.parent
    ws = out_root / f"{datetime.now():%Y.%m.%d}_{team}_TexcorePlan"
    ws.mkdir(parents=True, exist_ok=True)
    files = []
    for f in sorted(src.rglob("*")):
        if f.is_file() and not f.name.startswith(("~$", ".")) and "_TexcorePlan" not in str(f):
            files.append({"path": str(f), "name": f.name, "ext": f.suffix.lower(), "size": f.stat().st_size,
                          "supported": f.suffix.lower() in extractors.SUPPORTED})
    (ws / "inputs.json").write_text(json.dumps({"input_dir": str(src), "files": files}, ensure_ascii=False, indent=2), encoding="utf-8")
    State.new(ws, team=team, input_dir=str(src), edu_type=args.type or "미정")
    (ws / "run_log.md").write_text(f"# {team} 텍스코어 신청서 실행 로그\n\n- init {datetime.now():%Y-%m-%d %H:%M} · 입력 {len(files)}개\n", encoding="utf-8")
    print(f"WS={ws}")
    print(f"team={team} files={len(files)} unsupported={sum(1 for f in files if not f['supported'])} edu_type={args.type or '미정'}")
    return 0

def cmd_extract(args) -> int:
    ws = _ws_from_args(args)
    inputs = json.loads((ws / "inputs.json").read_text(encoding="utf-8"))
    ex = ws / "01_extract"; img_dir = ex / "images"; ex.mkdir(exist_ok=True); img_dir.mkdir(exist_ok=True)
    manifest = {"files": [], "total_chars": 0, "total_images": 0, "warnings": []}
    used: set[str] = set()
    for f in inputs["files"]:
        if not f["supported"]:
            manifest["warnings"].append(f"미지원 건너뜀: {f['name']}"); continue
        stem = Path(f["name"]).stem[:60]
        if stem in used:
            n = 2
            while f"{stem}_{n}" in used: n += 1
            stem = f"{stem}_{n}"
        used.add(stem)
        # 파일마다 이미지 하위 폴더를 따로 둔다 — 같은 stem의 pdf/pptx가 이미지 파일명을 덮어쓰던 문제(2026-10-27) 방지
        res = extractors.extract_file(f["path"], img_dir / stem)
        txt = ex / f"{stem}.txt"
        if res["text"].strip(): txt.write_text(res["text"], encoding="utf-8")
        manifest["files"].append({"name": f["name"], "kind": res["kind"], "text_path": str(txt) if res["text"].strip() else None,
                                  "chars": len(res["text"]), "images": res["images"], "warnings": res["warnings"]})
        manifest["total_chars"] += len(res["text"]); manifest["total_images"] += len(res["images"])
        manifest["warnings"].extend(f"{f['name']}: {w}" for w in res["warnings"])
    (ex / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(ws, f"extract files={len(manifest['files'])} chars={manifest['total_chars']} images={manifest['total_images']}")
    print(f"extracted files={len(manifest['files'])} chars={manifest['total_chars']:,} images={manifest['total_images']} warnings={len(manifest['warnings'])}")
    for w in manifest["warnings"][:20]: print("  !", w)
    return 0

def cmd_status(args) -> int:
    ws = _ws_from_args(args); st = State.load(ws)
    print(f"팀: {st.data['team']}  교육유형: {st.data.get('edu_type')}  WS: {ws}")
    for p in PHASES:
        ph = st.data["phases"][p]
        print(f"  {p:12s} {ph['status']:8s} {ph.get('finished') or ph.get('started') or ''}  {ph.get('note','')}")
    for g, v in st.data["gates"].items():
        print(f"  gate→{g}: {'OK' if v['ok'] else 'BLOCK'} {'; '.join(v['reasons'])}")
    return 0

# ───────────────────────── 검증·추적·게이트 ─────────────────────────
def cmd_validate(args) -> int:
    ws = _ws_from_args(args)
    f = Path(args.file) if args.file else None
    errs = validate.validate_phase(ws, args.target, f)
    warns = validate.lint_phase(ws, args.target, f)
    if errs:
        print(f"VALIDATE {args.target}: FAIL ({len(errs)})")
        for e in errs: print("  -", e)
    else:
        print(f"VALIDATE {args.target}: OK")
    if warns:
        print(f"LINT {args.target}: 경고 {len(warns)}건 (게이트는 막지 않지만 고칠 것)")
        for w in warns[:40]: print("  ~", w)
    return 1 if errs else 0

def cmd_trace(args) -> int:
    ws = _ws_from_args(args)
    try:
        rep = trace_numbers.run(ws, Path(args.file) if args.file else None)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[오류] {exc}"); return 1
    if rep["untraced"]:
        print(f"TRACE: FAIL — 미추적 숫자 {len(rep['untraced'])}건 (자료·증거에 없는 숫자는 만들지 마세요)")
        for u in rep["untraced"][:40]: print(f"  - {u['section_id']} {u['field']}: {u['token']}  ← {u['context']}")
        return 1
    print(f"TRACE: OK ({rep['sections']}섹션, 허용 토큰 {rep['allowed_tokens']}개)"); return 0

def cmd_gate(args) -> int:
    ws = _ws_from_args(args)
    ok, reasons = gate.check(ws, args.phase, accept_risk=args.accept_risk)
    print(f"GATE → phase {args.phase}: {'OK' if ok else 'BLOCK'}")
    for r in reasons: print("  -", r)
    return 0 if ok else 1

# ───────────────────────── 5. DESIGN: 그림 → 사양 → 주입 → QA ─────────────────────────
def _draft_file(ws: Path, given: str | None) -> Path:
    if given: return Path(given)
    return ws / "07_draft_v2.json" if (ws / "07_draft_v2.json").exists() else ws / "04_draft_v1.json"

def cmd_figures(args) -> int:
    ws = _ws_from_args(args)
    import make_figures  # noqa: E402  (tp-figures 모듈)
    doc = json.loads(_draft_file(ws, args.file).read_text(encoding="utf-8"))
    out = ws / "08_figures"; out.mkdir(exist_ok=True)
    figs = []
    for f in doc.get("figures", []):
        # font_scale 기본 1.3: 1600px 폭 그림을 150mm로 넣으면 26px≈6.9pt라 작다 → 1.3배(≈9pt)가 인쇄 가독 하한
        figs.append({"id": f["id"], "type": f["type"], "width_px": int(f.get("width_px") or 1600), "font_scale": float(f.get("font_scale") or 1.3), "data": f.get("data", {})})
    spec = {"figures": figs}
    (out / "figures_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    report = make_figures.render_all(spec, out)
    (out / "figures_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in report if r.get("ok")); bad = [r for r in report if not r.get("ok")]
    _log(ws, f"figures ok={ok} fail={len(bad)}")
    print(f"FIGURES: {ok}/{len(report)} 렌더 완료 → {out}")
    for r in bad: print(f"  ! {r.get('id')}: {r.get('error')}")
    return 0 if not bad else 1

def cmd_fillspec(args) -> int:
    ws = _ws_from_args(args)
    if getattr(args, "remove_page_breaks", False) or getattr(args, "clear_unfilled", False):
        opt_p = ws / "08_fill_options.json"
        opts = json.loads(opt_p.read_text(encoding="utf-8")) if opt_p.exists() else {}
        if args.remove_page_breaks: opts["remove_page_breaks"] = True
        if args.clear_unfilled: opts["clear_unfilled"] = True
        opt_p.write_text(json.dumps(opts, ensure_ascii=False, indent=2), encoding="utf-8")
    p = build_fillspec.build(ws, _draft_file(ws, args.file))
    spec = json.loads(p.read_text(encoding="utf-8"))
    n_blocks = sum(len(v) for v in spec["sections"].values())
    print(f"FILLSPEC: {p}  sections={len(spec['sections'])} blocks={n_blocks} replacements={len(spec['replacements'])} trl={spec['trl']}")
    return 0

def _build_paths(ws: Path):
    team = State.load(ws).data["team"]
    b = ws / "09_build"; b.mkdir(exist_ok=True)
    return b / f"{team}_사업신청서_v1.hwpx", b / f"{team}_사업신청서_v1.hwp", b / f"{team}_사업신청서_v1.pdf"

def cmd_fill(args) -> int:
    ws = _ws_from_args(args)
    import hwp_fill  # noqa: E402  (tp-hwpfill 모듈, Windows + 한글 필요)
    spec = Path(args.spec) if args.spec else ws / "08_fill_spec.json"
    if not spec.exists(): print("08_fill_spec.json 없음 — `harness fillspec` 먼저"); return 1
    master = Path(args.master) if args.master else MASTER
    if not master.exists(): print(f"템플릿 마스터 없음: {master}"); return 1
    hwpx, hwp, pdf = _build_paths(ws)
    rep = hwp_fill.fill(str(master), str(spec), str(hwpx), hwp=str(hwp), pdf=str(pdf))
    (ws / "09_build" / "fill_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    _log(ws, f"fill pages={rep.get('pages')} leftover={len(rep.get('leftover_tokens', []))}")
    print(f"FILL: {hwpx}  pages={rep.get('pages')} leftover_tokens={rep.get('leftover_tokens')} warnings={len(rep.get('warnings', []))}")
    for w in rep.get("warnings", [])[:20]: print("  !", w)
    return 0

def cmd_qa(args) -> int:
    ws = _ws_from_args(args)
    import render_qa  # noqa: E402  (tp-hwpfill 모듈)
    hwpx, _, pdf = _build_paths(ws)
    src = Path(args.src) if args.src else hwpx
    if not src.exists(): print("FILL 먼저 실행"); return 1
    out = ws / "09_build" / "qa"
    # fill이 만든 PDF가 있으면 COM 재렌더 없이 그 PDF로 검수한다
    rep = render_qa.render(str(src), str(out), dpi=int(args.dpi or 110), pdf=str(pdf) if (not args.src and pdf.exists()) else None)
    lim = validate.load_limits()
    pages = rep.get("pages", 0)
    # render_qa가 쪽수 초과·남은 토큰·삭제할 양식 문구를 blocking으로, 빈 섹션·라벨 잔존·빈 쪽을 warnings로 돌려준다
    blocking = [str(b) for b in (rep.get("blocking") or [])]
    if pages > lim["page_total_max"] and not any("쪽수" in b for b in blocking):
        blocking.append(f"쪽수 {pages} > {lim['page_total_max']} — 본문을 줄이거나 표·그림 크기를 줄일 것(remove_page_breaks도 검토)")
    warns = [str(w) for w in (rep.get("warnings") or [])] + [f"[info] {i}" for i in (rep.get("info") or [])]
    md = [f"# QA — {src.name}", "", f"- 쪽수: {pages} (상한 {lim['page_total_max']})", f"- 이미지 수: {rep.get('images', '?')}",
          f"- PNG: {out}", "", f"BLOCKING: {len(blocking)}", *[f"- [B] {b}" for b in blocking], "", f"WARN: {len(warns)}", *[f"- [W] {w}" for w in warns], "",
          "## 육안 검수 항목(tp-designer가 PNG를 보고 기록)", "- [ ] 그림이 본문 흐름 안에 있고 잘리지 않음", "- [ ] 캡션·출처·'→ 증명'이 그림 아래에 붙어 있음",
          "- [ ] 표가 쪽 경계에서 어색하게 갈라지지 않음", "- [ ] 결론 박스(callout)가 각 섹션 맨 앞에 있음", "- [ ] 체크박스 ■ 전환·표지 인적사항 정확", "- [ ] 작성요령 박스 없음"]
    (ws / "09_build" / "qa_report.md").write_text("\n".join(md), encoding="utf-8")
    (ws / "09_build" / "qa_report.json").write_text(json.dumps({"pages": pages, "blocking": blocking, "warnings": warns, "render": rep}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    _log(ws, f"qa pages={pages} blocking={len(blocking)} warn={len(warns)}")
    print("\n".join(md[:12]))
    return 0 if not blocking else 1

def cmd_final(args) -> int:
    ws = _ws_from_args(args); team = State.load(ws).data["team"]
    hwpx, hwp, pdf = _build_paths(ws)
    fin = ws / "10_final"; fin.mkdir(exist_ok=True)
    copied = []
    for src, name in ((hwpx, f"{team}_사업신청서.hwpx"), (hwp, f"{team}_사업신청서.hwp"), (pdf, f"{team}_사업신청서.pdf")):
        if src.exists():
            shutil.copy2(src, fin / name); copied.append(name)
    qa = ws / "09_build" / "qa"
    if qa.exists():
        dst = fin / "qa_png"; shutil.rmtree(dst, ignore_errors=True); shutil.copytree(qa, dst)
    _log(ws, f"final copied={copied}")
    print(f"FINAL: {fin}  복사={copied}")
    return 0

SUBCOMMANDS = {"init": cmd_init, "extract": cmd_extract, "status": cmd_status, "validate": cmd_validate, "trace": cmd_trace, "gate": cmd_gate,
               "figures": cmd_figures, "fillspec": cmd_fillspec, "fill": cmd_fill, "qa": cmd_qa, "final": cmd_final}

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="harness.py", description="texcore-plan 하네스")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("input_dir"); p.add_argument("--team"); p.add_argument("--out"); p.add_argument("--type", choices=["해외", "국내"])
    for name in ("extract", "status", "fillspec", "final", "figures"):
        p = sub.add_parser(name); p.add_argument("--ws", required=True)
        if name in ("fillspec", "figures"): p.add_argument("--file")
        if name == "fillspec":
            p.add_argument("--remove-page-breaks", dest="remove_page_breaks", action="store_true", help="Ⅲ·Ⅳ 장 강제 쪽 나눔 해제(10쪽 초과 시). 08_fill_options.json에 저장되어 재빌드에도 유지")
            p.add_argument("--clear-unfilled", dest="clear_unfilled", action="store_true")
    p = sub.add_parser("validate"); p.add_argument("target", choices=list(validate._TARGET_FILES)); p.add_argument("--ws", required=True); p.add_argument("--file")
    p = sub.add_parser("trace"); p.add_argument("--ws", required=True); p.add_argument("--file")
    p = sub.add_parser("gate"); p.add_argument("phase", choices=["2", "3", "4", "5", "6", "final"]); p.add_argument("--ws", required=True); p.add_argument("--accept-risk", action="store_true")
    p = sub.add_parser("fill"); p.add_argument("--ws", required=True); p.add_argument("--spec"); p.add_argument("--master")
    p = sub.add_parser("qa"); p.add_argument("--ws", required=True); p.add_argument("--src"); p.add_argument("--dpi")
    return ap

def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return SUBCOMMANDS[args.cmd](args)
    except WorkspaceError as exc:
        print(f"[오류] {exc}"); return 1

if __name__ == "__main__":
    raise SystemExit(main())
