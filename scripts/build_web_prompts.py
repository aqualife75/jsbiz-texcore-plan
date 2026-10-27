# -*- coding: utf-8 -*-
"""web/텍스코어_신청서_프롬프트북.md → docs/web.html (복사 버튼이 달린 프롬프트 북 페이지).

사용: python scripts/build_web_prompts.py [--src web/텍스코어_신청서_프롬프트북.md] [--out docs/web.html]

외부 라이브러리 없이 마크다운의 부분집합만 변환한다:
  # / ## / ###  제목 · 문단 · - 불릿 · 1. 번호 목록 · | 표 | · > 인용 · ```prompt 펜스(복사 버튼 프롬프트) · 기타 펜스(<pre>)
  **굵게** · `코드` · [링크](url)
"""
from __future__ import annotations
import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "web" / "텍스코어_신청서_프롬프트북.md"
OUT = ROOT / "docs" / "web.html"

CSS = """
:root{--brand:#FF385C;--brand-soft:#FFE4EA;--text:#1E293B;--muted:#94A3B8;--heading:#374151;--bg:#F8FAFC;--surface:#fff;--surface-alt:#F1F5F9;--border:#E2E8F0;--code-bg:#1E293B;--navy:#1B3A5C}
*{box-sizing:border-box}body{margin:0;font-family:'Pretendard','Apple SD Gothic Neo','Malgun Gothic',sans-serif;font-size:15px;line-height:1.75;color:var(--text);background:var(--bg);word-break:keep-all}
header{background:var(--surface);border-bottom:1px solid var(--border);padding:32px 24px}.wrap{max-width:960px;margin:0 auto;padding:0 24px}
h1{font-size:26px;font-weight:700;color:var(--brand);letter-spacing:-.02em;margin:0 0 8px}h2{font-size:21px;font-weight:700;margin:48px 0 16px;padding-left:12px;border-left:4px solid var(--brand);letter-spacing:-.02em}
h3{font-size:17px;font-weight:600;color:var(--heading);margin:24px 0 8px}p{margin:10px 0}.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600;background:var(--brand-soft);color:var(--brand)}
nav{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:12px}nav a{color:var(--heading);text-decoration:none;font-size:13px}
table{width:100%;border-collapse:collapse;font-size:14px;margin:12px 0}th,td{border-bottom:1px solid var(--border);padding:7px 10px;text-align:left;vertical-align:top}th{background:var(--surface-alt)}
ul,ol{padding-left:22px}li{margin:4px 0}blockquote{margin:12px 0;padding:10px 16px;background:var(--brand-soft);border-radius:8px}
.prompt{position:relative;background:var(--code-bg);color:#E2E8F0;border-radius:10px;margin:16px 0;border:1px solid #0f172a}
.prompt pre{margin:0;padding:18px 20px 18px;white-space:pre-wrap;word-break:break-word;font:13.5px/1.7 'Pretendard','Malgun Gothic',monospace;max-height:520px;overflow:auto}
.prompt .bar{display:flex;align-items:center;justify-content:space-between;padding:8px 12px 8px 16px;border-bottom:1px solid #334155;font-size:12px;color:#CBD5E1}
.prompt button{border:0;background:var(--brand);color:#fff;border-radius:6px;padding:5px 12px;font-size:12px;font-weight:600;cursor:pointer}
pre.plain{background:var(--surface-alt);padding:12px 16px;border-radius:8px;overflow:auto;font-size:13px;white-space:pre-wrap}code{font-size:.92em;background:var(--surface-alt);padding:1px 5px;border-radius:4px}
.prompt code{background:transparent;padding:0}footer{color:var(--muted);font-size:13px;padding:48px 24px;text-align:center}
.toc{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 20px;margin:20px 0}.toc a{display:inline-block;margin:3px 14px 3px 0;color:var(--heading);text-decoration:none;font-size:14px}
@media(max-width:720px){.wrap{padding:0 16px}.prompt pre{max-height:none}}
"""

JS = """function copyPrompt(b){const t=b.closest('.prompt').querySelector('pre').innerText;navigator.clipboard.writeText(t).then(()=>{b.textContent='복사됨';setTimeout(()=>b.textContent='프롬프트 복사',1400)}).catch(()=>{const r=document.createRange();r.selectNodeContents(b.closest('.prompt').querySelector('pre'));const s=getSelection();s.removeAllRanges();s.addRange(r);b.textContent='선택됨 — Ctrl+C'})}"""


def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
    return s


def slug(text: str, used: set) -> str:
    base = re.sub(r"[^0-9A-Za-z가-힣]+", "-", text).strip("-")[:40] or "s"
    s, i = base, 2
    while s in used:
        s = f"{base}-{i}"; i += 1
    used.add(s); return s


def convert(md: str) -> tuple[str, list[tuple[str, str]], int]:
    lines = md.splitlines()
    out: list[str] = []; toc: list[tuple[str, str]] = []; used: set = set()
    i = 0; n_prompts = 0; title = ""
    list_tag = None; in_table = False; table_rows: list[list[str]] = []

    def close_list():
        nonlocal list_tag
        if list_tag:
            out.append(f"</{list_tag}>"); list_tag = None

    def flush_table():
        nonlocal in_table, table_rows
        if not in_table:
            return
        rows = [r for r in table_rows if not all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in r)]
        if rows:
            out.append("<div style='overflow-x:auto'><table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead><tbody>")
            for r in rows[1:]:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table></div>")
        in_table = False; table_rows = []

    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            close_list(); flush_table()
            lang = ln[3:].strip().lower(); buf = []; i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1
            body = html.escape("\n".join(buf))
            if lang == "prompt":
                n_prompts += 1
                out.append(f'<div class="prompt" id="prompt-{n_prompts}"><div class="bar"><span>프롬프트 {n_prompts} · 그대로 붙여넣기</span><button type="button" onclick="copyPrompt(this)">프롬프트 복사</button></div><pre>{body}</pre></div>')
            else:
                out.append(f'<pre class="plain">{body}</pre>')
            continue
        if ln.startswith("|") and ln.rstrip().endswith("|"):
            close_list()
            in_table = True; table_rows.append([c.strip() for c in ln.strip().strip("|").split("|")]); i += 1; continue
        flush_table()
        m = re.match(r"^(#{1,3})\s+(.*)$", ln)
        if m:
            close_list()
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 1:
                title = text; i += 1; continue
            sid = slug(text, used)
            if level == 2:
                toc.append((sid, text))
            out.append(f"<h{level} id=\"{sid}\">{inline(text)}</h{level}>"); i += 1; continue
        if ln.startswith(">"):
            close_list(); out.append(f"<blockquote>{inline(ln.lstrip('> ').strip())}</blockquote>"); i += 1; continue
        m = re.match(r"^\s*[-*]\s+(.*)$", ln)
        if m:
            if list_tag != "ul":
                close_list(); out.append("<ul>"); list_tag = "ul"
            out.append(f"<li>{inline(m.group(1))}</li>"); i += 1; continue
        m = re.match(r"^\s*\d+[.)]\s+(.*)$", ln)
        if m:
            if list_tag != "ol":
                close_list(); out.append("<ol>"); list_tag = "ol"
            out.append(f"<li>{inline(m.group(1))}</li>"); i += 1; continue
        if not ln.strip():
            close_list(); i += 1; continue
        close_list(); out.append(f"<p>{inline(ln.strip())}</p>"); i += 1
    close_list(); flush_table()
    return "\n".join(out), toc, n_prompts, title  # type: ignore[return-value]


def build(src: Path = SRC, out: Path = OUT) -> dict:
    md = src.read_text(encoding="utf-8")
    body, toc, n_prompts, title = convert(md)  # type: ignore[misc]
    nav = "".join(f'<a href="#{sid}">{html.escape(t)}</a>' for sid, t in toc)
    page = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title or '텍스코어 사업신청서 프롬프트 북')}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css">
<style>{CSS}</style>
</head>
<body>
<header><div class="wrap"><span class="badge">정석Biz · Gemini·ChatGPT 웹용</span>
<h1>{html.escape(title or '텍스코어 사업신청서 프롬프트 북')}</h1>
<p>Claude Code·Codex 없이 <b>브라우저 채팅만으로</b> 같은 순서(자료 판독 → 결론 표 → 본문 → 5인 모의심사 → 근거 조사 → 그림·표 → 10쪽 맞추기 → 심사 대비)를 밟습니다. 각 프롬프트의 <b>복사</b> 버튼을 눌러 ChatGPT 또는 Gemini에 그대로 붙여넣으세요. 결과는 한글 양식에 직접 옮깁니다. 플러그인·Codex 버전은 <a href="index.html">사용법 가이드</a>에 있습니다.</p>
<nav>{nav}</nav></div></header>
<main class="wrap">
{body}
</main>
<footer>정석Biz · 이동건 · <a href="https://www.youtube.com/@정석Biz">유튜브 @정석Biz</a> · <a href="https://github.com/aqualife75/jsbiz-texcore-plan">GitHub</a> · <a href="index.html">플러그인·Codex 가이드</a> · 원본 마크다운: <a href="https://github.com/aqualife75/jsbiz-texcore-plan/blob/main/web/%ED%85%8D%EC%8A%A4%EC%BD%94%EC%96%B4_%EC%8B%A0%EC%B2%AD%EC%84%9C_%ED%94%84%EB%A1%AC%ED%94%84%ED%8A%B8%EB%B6%81.md">web/</a></footer>
<script>{JS}</script>
</body></html>
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return {"out": str(out), "prompts": n_prompts, "sections": len(toc), "title": title}


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(SRC)); ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    r = build(Path(a.src), Path(a.out))
    print(f"{r['out']}  프롬프트 {r['prompts']}개 · 절 {r['sections']}개 · 제목 '{r['title']}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
