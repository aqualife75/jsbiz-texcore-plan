#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검수된 산출물을 교육생용 결과 폴더(결과물/)에 게시한다(표준 라이브러리만).

사용: <python> .agents/skills/texcore-plan/scripts/publish_results.py --project . [--ws <워크스페이스>]

- WS를 주지 않으면 project.json의 work_dir 안에서 가장 최근 갱신된 *_TexcorePlan 폴더를 쓴다.
- 결과물/{YYYYMMDD-HHMM}_{팀}/ 에 복사: 10_final/*(hwp·hwpx·pdf·심사대비_패키지.md·팀_확인사항.md·qa_png/),
  신청서_본문초안.md(07_draft_v2 또는 04_draft_v1을 읽기 좋은 마크다운으로), 도식/(08_figures PNG), 팀_질문지.md,
  주입사양.json(08_fill_spec.json — 한글이 없는 환경에서 Windows로 가져가 마무리할 때)
- 결과보기.html을 그 폴더와 결과물/ 루트(최신 결과 링크)에 쓴다. 상태는 state.json의 gate 기록으로 구분한다:
  gate final OK + hwpx 있음 → "초안 완료(팀 확인사항 반영 전)" / 주입 사양만 있음 → "초안(한글 주입 전)" / 그 외 → "작업 중"
"""
from __future__ import annotations
import argparse
import html
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

TITLE = "정석biz 노하우 · 텍스코어 사업신청서"


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def latest_ws(project: Path, work_dir: str) -> Path | None:
    cands = [d for d in (project / work_dir).glob("*_TexcorePlan") if (d / "state.json").is_file()]
    if not cands:
        return None
    return max(cands, key=lambda d: (d / "state.json").stat().st_mtime)


# ───────────── 초안 JSON → 마크다운 ─────────────
def _table_md(columns, rows) -> str:
    cols = [str(c) for c in (columns or [])]
    if not cols and rows:
        cols = [f"열{i+1}" for i in range(len(rows[0]))]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows or []:
        cells = [str(c).replace("|", "\\|").replace("\n", " ") for c in (r if isinstance(r, list) else [r])]
        cells += [""] * (len(cols) - len(cells))
        out.append("| " + " | ".join(cells[:len(cols)]) + " |")
    return "\n".join(out)


def draft_to_markdown(doc: dict, team: str) -> str:
    L = [f"# {team} 텍스코어 사업신청서 — 본문 초안", "", "> 하네스가 만든 초안입니다. 한글 양식에 옮길 때 칸 순서는 아래 제목을 따르고, `[기입 필요]`·`[확보 필요]`는 팀이 채웁니다.", ""]
    cover = doc.get("cover") or {}
    if cover:
        L += ["## 표지", ""]
        for k, lab in (("org", "소속 기관"), ("team_ko", "탐색팀명"), ("team_en", "탐색팀명(영문)"), ("item_ko", "아이템"), ("item_en", "아이템(영문)"),
                       ("tech_field", "기술 분야"), ("industry", "산업"), ("region", "권역"), ("date", "작성일")):
            if cover.get(k):
                L.append(f"- {lab}: {cover[k]}")
        for role in ("EL", "PM", "PI"):
            p = cover.get(role) or {}
            if p.get("name"):
                L.append(f"- {role}: {p.get('name')} · {p.get('org_dept', '')} · {p.get('degree_status', '')} · {p.get('phone', '')} · {p.get('email', '')}")
        L.append("")
    for s in doc.get("sections", []):
        L += [f"## {s.get('title') or s.get('id')}", ""]
        if s.get("governing"):
            L += [f"**결론:** {s['governing']}", ""]
        for b in s.get("blocks", []):
            t = b.get("type")
            if t == "callout":
                L += [f"> **{b.get('text', '')}**", ""]
            elif t == "heading":
                L += [f"### {b.get('text', '')}", ""]
            elif t == "subheading":
                L += [f"**□ {b.get('text', '')}**", ""]
            elif t == "para":
                L += [b.get("text", ""), ""]
            elif t == "bullets":
                L += [f"- {it}" for it in b.get("items", [])] + [""]
            elif t == "table":
                if b.get("caption"):
                    L.append(f"**{b['caption']}**")
                L += [_table_md(b.get("columns"), b.get("rows")), ""]
                if b.get("source"):
                    L += [f"출처: {b['source']}", ""]
            elif t in ("figure", "figure_ref"):
                L += [f"[그림] {b.get('caption', '')}  (파일: {b.get('figure_id') or ', '.join(i.get('path', '') for i in b.get('images', []))})"]
                if b.get("proves"):
                    L.append(f"→ 증명: {b['proves']}")
                if b.get("source"):
                    L.append(f"출처: {b['source']}")
                L.append("")
    ft = doc.get("fixed_tables") or {}
    if ft:
        L += ["## 고정 표", ""]
        for key, lab in (("patents", "특허 출원/등록 실적"), ("other_ip", "기타 지식재산권"), ("ip_relations", "핵심기술 권리관계"),
                         ("team_members", "탐색팀 구성"), ("team_careers", "구성원 경력")):
            rows = ft.get(key) or []
            if rows:
                L += [f"### {lab}", _table_md(None, rows), ""]
        if ft.get("trl"):
            L += [f"### TRL: {ft['trl'].get('level', '')}", ""]
    if doc.get("to_secure"):
        L += ["## 확보 필요 목록", ""] + [f"- {x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)}" for x in doc["to_secure"]] + [""]
    return "\n".join(L)


# ───────────── 게시 ─────────────
def page(title: str, body: str) -> str:
    return ('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(title)}</title><style>"
            'body{font:16px/1.75 "Malgun Gothic","Apple SD Gothic Neo",sans-serif;background:#f4f7fc;color:#183151;margin:0}'
            "main{max-width:900px;margin:auto;padding:48px 24px}h1{font-size:30px;line-height:1.35;letter-spacing:-.5px}"
            "h2{margin-top:36px;font-size:20px}a{color:#2457d6;text-underline-offset:4px}.badge{display:inline-block;padding:4px 12px;border-radius:999px;font-weight:700;background:#fff;border:1px solid #dce5f0}"
            ".card{background:#fff;padding:20px 24px;border-radius:12px;margin:14px 0;border:1px solid #dce5f0}.files a{display:inline-block;border:1px solid #dce5f0;border-radius:8px;padding:10px 14px;margin:6px 8px 6px 0;background:#fff}"
            "table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid #dce5f0;padding:6px 10px;text-align:left}small{color:#53677e}li{margin:6px 0}"
            f"</style><main><p><small>{html.escape(TITLE)}</small></p><h1>{html.escape(title)}</h1>{body}</main></html>")


def link(rel: str, label: str) -> str:
    return f'<a href="{quote(rel, safe="/")}">{html.escape(label)}</a>'


def publish(project: Path, ws: Path | None) -> Path:
    project = Path(project).resolve()
    cfg = _read_json(project / "project.json") or {}
    work_dir = cfg.get("work_dir", "work")
    ws = Path(ws).resolve() if ws else latest_ws(project, work_dir)
    if ws is None or not (ws / "state.json").is_file():
        raise SystemExit("게시할 워크스페이스가 없습니다. 먼저 신청서 작성을 진행하세요.")
    state = _read_json(ws / "state.json") or {}
    team = state.get("team") or cfg.get("team_name") or "우리팀"
    gates = state.get("gates", {})
    final_dir = ws / "10_final"
    hwpx = next(iter(final_dir.glob("*_사업신청서.hwpx")), None) if final_dir.is_dir() else None
    fill_spec = ws / "08_fill_spec.json"
    if hwpx and gates.get("final", {}).get("ok"):
        status, badge = "초안 완료(팀 확인사항 반영 전)", "✅"
    elif hwpx:
        status, badge = "초안(최종 검수 미통과 — 검수 보고 확인)", "⚠️"
    elif fill_spec.is_file():
        status, badge = "초안(한글 주입 전 — Windows+한글에서 마무리 필요)", "🟡"
    else:
        status, badge = "작업 중(아직 게시할 신청서가 없음)", "⏳"

    dest_root = project / "결과물"; dest_root.mkdir(exist_ok=True)
    dest = dest_root / f"{datetime.now():%Y%m%d-%H%M}_{team}"
    dest.mkdir(parents=True, exist_ok=True)
    files: list[tuple[str, str]] = []  # (상대경로, 라벨)

    if final_dir.is_dir():
        for f in sorted(final_dir.iterdir()):
            if f.is_file():
                shutil.copy2(f, dest / f.name); files.append((f.name, f.name))
            elif f.is_dir() and f.name == "qa_png":
                shutil.copytree(f, dest / "쪽별_PNG", dirs_exist_ok=True); files.append(("쪽별_PNG/", "쪽별 PNG 폴더"))
    draft_p = next((p for p in (ws / "07_draft_v2.json", ws / "04_draft_v1.json") if p.is_file()), None)
    if draft_p:
        doc = _read_json(draft_p) or {}
        (dest / "신청서_본문초안.md").write_text(draft_to_markdown(doc, team), encoding="utf-8")
        files.append(("신청서_본문초안.md", "신청서 본문 초안(md)"))
    figs = ws / "08_figures"
    if figs.is_dir() and any(figs.glob("*.png")):
        (dest / "도식").mkdir(exist_ok=True)
        for p in figs.glob("*.png"):
            shutil.copy2(p, dest / "도식" / p.name)
        files.append(("도식/", "증거 도식 PNG"))
    if (ws / "02_team_questions.md").is_file():
        shutil.copy2(ws / "02_team_questions.md", dest / "팀_질문지.md"); files.append(("팀_질문지.md", "팀 질문지"))
    if fill_spec.is_file() and not hwpx:
        shutil.copy2(fill_spec, dest / "주입사양.json"); files.append(("주입사양.json", "한글 주입 사양(JSON)"))

    summary = _read_json(ws / "05_review" / "summary.json") or {}
    qa = _read_json(ws / "09_build" / "qa_report.json") or {}
    scores = summary.get("item_scores") or {}
    pf = summary.get("pf") or {}
    body = [f'<p><span class="badge">{badge} {html.escape(status)}</span> &nbsp; <small>팀: {html.escape(team)} · 게시 {datetime.now():%Y-%m-%d %H:%M} · 워크스페이스 {html.escape(ws.name)}</small></p>']
    body.append('<div class="card"><h2 style="margin-top:0">파일</h2><div class="files">' + "".join(link(r, l) for r, l in files) + "</div></div>")
    if scores:
        rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>" for k, v in scores.items())
        body.append('<div class="card"><h2 style="margin-top:0">모의심사(실제 평가표 기준, 참고치)</h2><table><tr><th>항목</th><th>점수</th></tr>' + rows + "</table>"
                    + (f"<p>해외형 P/F: 영어 {html.escape(str(pf.get('english', 'N/A')))} · 미국 시장 {html.escape(str(pf.get('us_market', 'N/A')))}</p>" if pf else "")
                    + "<p><small>목표선 80점. 공개판 모의심사는 일반화된 기준이며 실제 선정을 예측하지 않습니다.</small></p></div>")
    if qa:
        body.append(f'<div class="card"><h2 style="margin-top:0">쪽 검수</h2><p>쪽수 {html.escape(str(qa.get("pages", "?")))} / 최대 10 · BLOCKING {len(qa.get("blocking") or [])} · 경고 {len(qa.get("warnings") or [])}</p></div>')
    body.append('<div class="card"><h2 style="margin-top:0">다음에 할 일</h2><ol>'
                "<li><b>팀_확인사항.md</b>를 먼저 읽고 비어 있는 값(자격 요건·인적사항·특허번호·인터뷰 수)을 채우세요.</li>"
                "<li>답을 <b>02_team_answers.md</b>로 적어 자료넣는곳에 넣고 Codex에게 “4단계부터 다시 해줘”라고 말하세요.</li>"
                "<li>한글에서 최종 파일을 열어 소리 내어 읽고, 공고의 제출 형식·파일명·마감일을 직접 확인하세요.</li></ol>"
                "<p><small>이 결과는 초안입니다. 모든 문장과 숫자의 책임은 팀에게 있습니다.</small></p></div>")
    (dest / "결과보기.html").write_text(page(f"{team} 사업신청서 — 결과", "".join(body)), encoding="utf-8")
    # 루트 결과보기: 최신 결과 폴더로 링크
    root_body = body[0] + f'<div class="card"><h2 style="margin-top:0">최신 결과 폴더</h2><p>{link(dest.name + "/결과보기.html", dest.name + " 열기")}</p></div>' + "".join(body[1:]).replace('href="', f'href="{quote(dest.name)}/')
    (dest_root / "결과보기.html").write_text(page(f"{team} 사업신청서 — 최신 결과", root_body), encoding="utf-8")
    print(f"게시 완료: {dest}\n상태: {status}\n결과보기: {dest_root / '결과보기.html'}")
    return dest


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="검수된 신청서 산출물을 결과물/ 폴더에 게시합니다.")
    ap.add_argument("--project", type=Path, default=Path("."))
    ap.add_argument("--ws", type=Path)
    a = ap.parse_args(argv)
    publish(a.project, a.ws)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
