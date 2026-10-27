# -*- coding: utf-8 -*-
"""텍스코어 사업신청서용 시각자료(증거 이미지·도식) 생성기.

spec(JSON) → 유형별 HTML 조판 → Chrome 헤드리스 스크린샷 → 순백 여백 트리밍 → `{id}.png`
Playwright 불필요. 폰트는 로컬 설치 폰트만 쓴다(CDN 없음, 오프라인 동작).

CLI:
    python -X utf8 make_figures.py --spec spec.json --out outdir [--scale 2] [--only id1,id2] [--keep-html]
라이브러리:
    from make_figures import render_all, render_one
    render_all(spec: dict | 경로, out_dir) -> list[dict]
    render_one(fig: dict, out_dir, base_dir=None) -> dict

spec 형식:
    {"figures": [{"id": "fig_comp", "type": "<유형>", "width_px": 1600, "font_scale": 1.0,
                  "title": "(선택) 상단 작은 라벨", "notice": "(선택) 하단 고지, 예: 설명용 샘플", "data": {...}}]}
지원 유형(12): competitor_matrix, tam_sam_som, tech_concept, trl_ladder, gantt_milestones, cost_table,
               team_org, evidence_card, evidence_board, kpi_strip, prototype_stages, customer_profile
결과: out_dir/figures_report.json = [{"id","type","file","w","h","ok","error","warnings","ink"}]
      file은 out_dir 기준 파일명, w·h는 최종 PNG 픽셀, warnings는 넘침·이미지 누락·숫자 불일치 등 검수 경고.
이미지 경로(data.image 등)는 절대경로 또는 spec 파일 폴더 기준 상대경로.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from capture_evidence import find_chrome  # noqa: E402  (Chrome/Edge 경로 OS 자동 감지 재사용)

CSS_PATH = HERE.parent / "assets" / "figure_styles.css"
DEFAULT_WIDTH = 1600
DEFAULT_SCALE = 2
BODY_PAD = 24          # HTML body 여백(CSS px) — figure_styles.css의 body padding과 같아야 한다
TRIM_PAD = 24          # 트리밍 후 남길 여백(CSS px, 저장 시 scale배)
FIRST_HEIGHT = 3000    # 첫 촬영 창 높이(CSS px). 그림이 더 길면 실측 높이로 다시 찍는다.
DOC_MM_PER_1600 = 150  # PNG DPI 메타데이터: 폭 1600 CSS px = 150mm(문서 삽입 '원래 크기' 기준)

TRL_NAMES = ["기본원리 파악", "기본개념 정립", "기능 및 개념 검증", "연구실 환경 테스트", "유사환경 테스트",
             "파일럿 현장 테스트", "상용모델 개발", "실제환경 최종 테스트", "상용운영"]

# 렌더 후 페이지 안에서 크기·넘침을 재서 <body data-metrics>에 남긴다(--dump-dom으로 회수).
METRICS_JS = r"""
(function(){
  function desc(el){
    var c = (typeof el.className === 'string') ? el.className.trim() : '';
    var t = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 24);
    return el.tagName.toLowerCase() + (c ? '.' + c.split(/\s+/).join('.') : '') + ' "' + t + '"';
  }
  function measure(){
    var fig = document.querySelector('.fig'); var r = fig.getBoundingClientRect(); var issues = [];
    var all = fig.querySelectorAll('*');
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      if (el.closest('[data-nocheck]') || el.closest('svg')) continue;
      var cs = getComputedStyle(el);
      if (cs.display === 'inline' || cs.display === 'contents' || cs.display === 'none') continue;
      if (el.tagName === 'IMG') { if (!(el.complete && el.naturalWidth > 0)) issues.push('이미지 로드 실패: ' + el.getAttribute('src')); continue; }
      if (el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 2) issues.push('가로 넘침: ' + desc(el) + ' (' + el.scrollWidth + '>' + el.clientWidth + ')');
      if (el.clientHeight > 0 && el.scrollHeight > el.clientHeight + 2) issues.push('세로 넘침: ' + desc(el) + ' (' + el.scrollHeight + '>' + el.clientHeight + ')');
      var er = el.getBoundingClientRect();
      if (er.width > 0 && (er.right > r.right + 1 || er.left < r.left - 1)) issues.push('그림 폭 밖으로 나감: ' + desc(el));
    }
    document.body.setAttribute('data-metrics', JSON.stringify({w: r.width, h: r.height, bottom: r.bottom + window.scrollY,
      right: r.right, issues: issues.slice(0, 30)}));
  }
  // 헤드리스+virtual-time에서는 requestAnimationFrame이 안 불리는 경우가 있어 setTimeout을 쓴다
  function go(){ setTimeout(measure, 50); }
  function ready(){ if (document.readyState === 'complete') go(); else window.addEventListener('load', go); }
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(ready); else ready();
})();
"""


# ───────────────────────── 공통 도우미 ─────────────────────────
class Ctx:
    """빌더에 넘기는 렌더 맥락(폭·글자배율·이미지 기준 폴더·경고 모음)."""

    def __init__(self, width: int, k: float, base_dir: Path | None):
        self.width = width
        self.k = k
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self.warnings: list[str] = []

    def warn(self, msg: str):
        self.warnings.append(msg)


def esc(s) -> str:
    """HTML 이스케이프 + 줄바꿈(\\n)을 <br>로. 가운뎃점(·) 앞뒤는 단어 결합(U+2060)으로 묶어
    '경사로 / ·문턱'처럼 줄 첫머리에 점이 오지 않게 한다(넘치면 CSS overflow-wrap이 알아서 끊는다)."""
    if s is None:
        return ""
    return html.escape(str(s)).replace("\n", "<br>").replace("·", "⁠·⁠")


def req(d: dict, key: str, typ=None):
    """필수 키 확인. 없으면 한국어 오류."""
    if not isinstance(d, dict) or key not in d or d[key] in (None, "", [], {}):
        raise ValueError(f"data.{key} 가 없습니다")
    v = d[key]
    if typ is not None and not isinstance(v, typ):
        raise ValueError(f"data.{key} 형식이 잘못되었습니다({typ.__name__} 필요)")
    return v


def nobr_ids(s, max_w: float | None = None, fs: float = 20) -> str:
    """특허·출원번호처럼 하이픈으로 이어진 숫자열(10-2026-0012345)은 줄바꿈되지 않게 묶는다.
    max_w(px)가 주어지면 그 폭 안에 들어가는 번호만 묶는다(안 들어가면 넘치느니 하이픈에서 끊긴다)."""
    def keep(m):
        tok = m.group(1)
        if max_w is not None and text_w(tok, fs) * 1.1 > max_w:
            return tok
        # 뒤에 바로 붙는 '(출원,' 등과 한 덩어리가 되지 않게 <wbr>로 줄바꿈 기회를 준다
        return f'<span style="white-space:nowrap">{tok}</span><wbr>'
    return re.sub(r"(\d[\d\-]*-\d[\d\-]*)", keep, esc(s))


def text_w(s, fs: float) -> float:
    """글자 폭 대략 추정(px). 한글·한자 ≈ 0.92em, 영숫자 ≈ 0.58em, 공백 ≈ 0.28em."""
    w = 0.0
    for ch in str(s or ""):
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3 or 0x3130 <= o <= 0x318F or 0x4E00 <= o <= 0x9FFF or 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF:
            w += 0.92 * fs
        elif ch == " ":
            w += 0.28 * fs
        elif ch in ".,:;'|!()[]·":
            w += 0.32 * fs
        else:
            w += 0.58 * fs
    return w


def fit_fs(text: str, max_w: float, fs: float, min_fs: float) -> float:
    """한 줄에 들어가도록 글자 크기를 줄인다(min_fs 아래로는 안 줄이고 줄바꿈에 맡김)."""
    need = text_w(text, fs)
    if need <= max_w:
        return fs
    return max(min_fs, fs * max_w / need)


def resolve_image(p, ctx: Ctx) -> str | None:
    """이미지 경로 → file:// URI. 없으면 None(+경고)."""
    if not p:
        return None
    path = Path(str(p))
    if not path.is_absolute():
        path = (ctx.base_dir / path)
    path = path.resolve()
    if not path.exists():
        ctx.warn(f"이미지 없음: {p}")
        return None
    return path.as_uri()


_UNITS = {"조": 1e12, "억": 1e8, "천만": 1e7, "백만": 1e6, "만": 1e4, "천": 1e3}


def parse_krw(s) -> float | None:
    """'1억 2,000만 원', '12,000,000원', '1,200천원' → 원 단위 숫자. 실패하면 None."""
    if s is None:
        return None
    t = str(s).replace(",", "").replace(" ", "")
    parts = re.findall(r"(\d+(?:\.\d+)?)(조|억|천만|백만|만|천)?", t)
    if not parts:
        return None
    return sum(float(n) * _UNITS.get(u, 1) for n, u in parts)


def first_number(s) -> float | None:
    m = re.findall(r"\d+(?:\.\d+)?", str(s or "").replace(",", ""))
    return float(m[0]) if len(m) == 1 else None


def fmt_pct(x: float) -> str:
    v = round(x * 100, 1)
    return f"{int(v)}%" if abs(v - round(v)) < 0.05 else f"{v}%"


ICONS = {
    "ok": '<svg class="{c}" viewBox="0 0 32 32"><circle cx="16" cy="16" r="11" fill="none" stroke="#059669" stroke-width="4"/></svg>',
    "mid": '<svg class="{c}" viewBox="0 0 32 32"><polygon points="16,4.5 28.5,26.5 3.5,26.5" fill="none" stroke="#D97706" stroke-width="4" stroke-linejoin="round"/></svg>',
    "ng": '<svg class="{c}" viewBox="0 0 32 32"><path d="M7.5 7.5 L24.5 24.5 M24.5 7.5 L7.5 24.5" stroke="#DC2626" stroke-width="4.2" stroke-linecap="round"/></svg>',
}
SYM = {"O": "ok", "o": "ok", "○": "ok", "◯": "ok", "●": "ok",
       "△": "mid", "▲": "mid", "◐": "mid",
       "X": "ng", "x": "ng", "×": "ng", "✕": "ng", "✗": "ng"}
SYM_LABEL = {"ok": "충족", "mid": "부분 충족", "ng": "미충족·없음"}

ARROW = ('<svg class="tc-arrow" viewBox="0 0 40 40" style="width:40px;height:40px">'
         '<path d="M4 20 H31 M21 9 L33 20 L21 31" fill="none" stroke="#1B3A5C" stroke-width="4" '
         'stroke-linecap="round" stroke-linejoin="round"/></svg>')


# ───────────────────────── 1. competitor_matrix ─────────────────────────
def b_competitor_matrix(d, ctx: Ctx) -> str:
    crit = req(d, "criteria", list)
    comps = req(d, "competitors", list)
    n = len(crit)
    for c in comps:
        cells = c.get("cells") or []
        if len(cells) != n:
            raise ValueError(f"경쟁사 '{c.get('name')}'의 cells 개수({len(cells)})가 criteria 개수({n})와 다릅니다")
    if not any(c.get("is_us") for c in comps):
        ctx.warn("is_us=true인 '우리' 열이 없습니다")
    first_w = 30 if len(comps) <= 4 else 24
    other = (100 - first_w) / max(1, len(comps))
    cols = f'<col style="width:{first_w}%">' + "".join(f'<col style="width:{other:.3f}%">' for _ in comps)
    head = ['<th class="cm-crit-h">비교 기준</th>']
    for c in comps:
        us = bool(c.get("is_us"))
        name = str(c.get("name", ""))
        tag = '<span class="us-tag">우리</span>' if us and "우리" not in name else ""
        head.append(f'<th class="{"us" if us else ""}">{esc(name)}{tag}</th>')
    used = []
    rows = []
    for i, cr in enumerate(crit):
        cr = cr if isinstance(cr, dict) else {"name": cr}
        tds = [f'<th class="cm-crit"><div class="cm-name">{esc(cr.get("name"))}</div>'
               + (f'<div class="cm-why">{esc(cr.get("why"))}</div>' if cr.get("why") else "") + "</th>"]
        for c in comps:
            v = str(c["cells"][i]).strip()
            kind = SYM.get(v)
            cls = []
            if c.get("is_us"):
                cls.append("us")
            if kind:
                used.append(kind)
                body = ICONS[kind].format(c="ic")
            else:
                cls.append("txt")
                body = esc(v)
            tds.append(f'<td class="{" ".join(cls)}">{body}</td>')
        rows.append(f'<tr class="{"last" if i == n - 1 else ""}">{"".join(tds)}</tr>')
    legend = ""
    if used:
        items = [f'<span>{ICONS[k].format(c="ic-s")} {SYM_LABEL[k]}</span>' for k in ("ok", "mid", "ng") if k in used]
        legend = f'<div class="cm-legend">{"".join(items)}</div>'
    note = f'<div class="fig-note">{esc(d.get("note"))}</div>' if d.get("note") else ""
    return (f'<table class="t cm"><colgroup>{cols}</colgroup><thead><tr>{"".join(head)}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>{legend}{note}')


# ───────────────────────── 2. tam_sam_som ─────────────────────────
def b_tam_sam_som(d, ctx: Ctx) -> str:
    parts = [("TAM", req(d, "tam", dict), "tam"), ("SAM", req(d, "sam", dict), "sam"), ("SOM", req(d, "som", dict), "som")]
    k = ctx.k
    D = int(min(660 * k, ctx.width * 0.44))
    ratio = {"tam": 1.0, "sam": 0.70, "som": 0.42}
    # 라벨 중심 y(원 컨테이너 기준)와 최대 폭: 바깥 띠의 가운데에 둔다(원은 아래 정렬 동심원)
    lab_y = {"tam": 0.15 * D, "sam": 0.44 * D, "som": 0.79 * D}
    lab_w = {"tam": 0.56 * D, "sam": 0.42 * D, "som": 0.36 * D}
    circles = "".join(f'<div class="tss-c {c}" style="width:{D * ratio[c]:.0f}px;height:{D * ratio[c]:.0f}px"></div>'
                      for _, _, c in parts)
    labs = []
    for key, p, c in parts:
        val = str(p.get("value", ""))
        fs = fit_fs(val, lab_w[c] * 0.9, 40 * k, 24 * k)
        nw = ";white-space:nowrap" if text_w(val, fs) <= lab_w[c] * 0.9 else ""   # 한 줄에 들어가면 '원'만 떨어지지 않게
        labs.append(f'<div class="tss-lab {c}" style="top:{lab_y[c]:.0f}px;width:{lab_w[c]:.0f}px">'
                    f'<div class="k">{key}</div><div class="v" style="font-size:{fs:.1f}px{nw}">{esc(val)}</div></div>')
    rows = []
    for key, p, c in parts:
        rows.append(f'<tr class="{c}"><td class="k"><b>{key}</b><span>{esc(p.get("label"))}</span></td>'
                    f'<td class="v">{esc(p.get("value"))}</td><td>{esc(p.get("calc"))}</td>'
                    f'<td class="src">{esc(p.get("source"))}</td></tr>')
    table = ('<table class="t tss-table"><colgroup><col style="width:20%"><col style="width:18%"><col style="width:42%">'
             '<col style="width:20%"></colgroup><thead><tr><th>구분</th><th>시장 규모</th><th>산식</th><th>출처</th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table>')
    note = f'<div class="fig-note">{esc(d.get("note"))}</div>' if d.get("note") else ""
    return (f'<div class="tss"><div class="tss-circles" data-nocheck style="width:{D}px;height:{D}px">{circles}{"".join(labs)}</div>'
            f'<div class="tss-table">{table}</div></div>{note}')


# ───────────────────────── 3. tech_concept ─────────────────────────
def _ev_badges(ev, max_w: float | None = None, fs: float = 20) -> str:
    """증거 문자열('A / B' 또는 줄바꿈 구분)을 배지 여러 개로. 비어 있으면 '근거 확보 필요' 점선 배지."""
    items = [s.strip() for s in re.split(r"\s+/\s+|\n", str(ev or "")) if s.strip()]
    if not items:
        return '<span class="badge" style="border-style:dashed;color:#64748B;border-color:#CBD5E1">근거 확보 필요</span>'
    out = []
    for s in items:
        bfs = fs
        ids = re.findall(r"\d[\d\-]*-\d[\d\-]*", s)
        if ids and max_w:
            need = max(text_w(t, 1) for t in ids) * 1.1
            if need * fs > max_w:                    # 번호가 한 줄에 안 들어가면 배지 글자를 최대 20% 줄여 본다
                bfs = max(fs * 0.8, max_w / need)
        st = f' style="font-size:{bfs:.1f}px"' if bfs != fs else ""
        out.append(f'<span class="badge"{st}>{nobr_ids(s, max_w, bfs)}</span>')
    return '<div style="display:flex;flex-direction:column;gap:8px;align-items:flex-start">' + "".join(out) + "</div>"


def b_tech_concept(d, ctx: Ctx) -> str:
    problem = req(d, "problem")
    comps = req(d, "components", list)
    outcome = req(d, "outcome")
    k = ctx.k
    n = max(1, len(comps))
    has_img = bool(d.get("image"))
    side = (220 if has_img else 260) * k          # 문제·변화 상자 폭
    # 가로 흐름일 때 기술 카드 1장의 폭 추정 → 너무 좁으면 세로 흐름(stack)으로 바꾼다
    mid = ctx.width - 2 * side - (220 * k + 16 if has_img else 0) - 2 * 40 - 4 * 16
    card = (mid - 32 - 16 * (n - 1)) / n
    stack = card < 210 * k
    if stack:
        card = (ctx.width - 32 - 16 * (n - 1)) / n
        comps_col = card < 240 * k                # 세로 흐름에서도 좁으면 카드를 한 줄에 하나씩
        if comps_col:
            card = ctx.width - 32
    badge_w = card - 34 - 28                      # 배지 안쪽 폭(번호 줄바꿈 방지 판단용)
    cards = []
    for i, c in enumerate(comps, 1):
        if not c.get("evidence"):
            ctx.warn(f"기술 덩어리 {i}({c.get('name')})에 evidence가 없습니다")
        cards.append(f'<div class="tc-comp"><div class="no">기술 {i}</div><div class="nm">{esc(c.get("name"))}</div>'
                     f'<div class="ds">{esc(c.get("desc"))}</div>'
                     f'<div class="ev">{_ev_badges(c.get("evidence"), badge_w, 20 * k)}</div></div>')
    img = ""
    if d.get("image"):
        uri = resolve_image(d.get("image"), ctx)
        if uri:
            img = f'<div class="tc-img"><img src="{uri}" alt=""></div>'
        else:
            img = ('<div class="tc-img"><div class="ev-missing" style="height:220px;font-size:var(--fs-cap)">'
                   '[이미지 확보 필요]</div></div>')
    if stack:
        # 세로 흐름: [문제] ↓ [기술 덩어리들] ↓ [변화] (+이미지). 폭이 좁거나 font_scale이 클 때
        down = ARROW.replace('class="tc-arrow"', 'class="tc-arrow" data-down')
        cc = ' style="flex-direction:column"' if comps_col else ""
        return (f'<div class="tc stack"><div class="tc-box tc-prob"><div class="lab">고객이 못 하는 일</div>{esc(problem)}</div>{down}'
                f'<div class="tc-mid"><div class="lab">핵심 기술 덩어리</div><div class="tc-comps"{cc}>{"".join(cards)}</div></div>{down}'
                f'<div class="tc-box tc-out"><div class="lab">고객에게 생기는 변화</div>{esc(outcome)}</div>{img}</div>')
    sb = f' style="flex-basis:{side:.0f}px"'
    return (f'<div class="tc"><div class="tc-box tc-prob"{sb}><div class="lab">고객이 못 하는 일</div>{esc(problem)}</div>{ARROW}'
            f'<div class="tc-mid"><div class="lab">핵심 기술 덩어리</div><div class="tc-comps">{"".join(cards)}</div></div>{ARROW}'
            f'<div class="tc-box tc-out"{sb}><div class="lab">고객에게 생기는 변화</div>{esc(outcome)}</div>{img}</div>')


# ───────────────────────── 4. trl_ladder ─────────────────────────
def b_trl_ladder(d, ctx: Ctx) -> str:
    try:
        cur = int(req(d, "current"))
        tgt = int(req(d, "target"))
    except (TypeError, ValueError):
        raise ValueError("data.current / data.target 은 1~9 정수여야 합니다")
    if not (1 <= cur <= 9 and 1 <= tgt <= 9):
        raise ValueError("TRL은 1~9 범위여야 합니다")
    if tgt < cur:
        ctx.warn(f"목표 TRL({tgt})이 현재({cur})보다 낮습니다")
    names = d.get("stages") if isinstance(d.get("stages"), list) and len(d.get("stages")) == 9 else TRL_NAMES
    period = d.get("target_period", "사업기간 내")
    k = ctx.k
    base_h, step = 150 * k, 30 * k
    # 단계명 글자 크기: 가장 긴 어절이 칸 안쪽 폭에 들어가게(좁은 폭에서 '기본원/리'처럼 어절 중간이 끊기지 않도록)
    inner = (ctx.width - 8 * 8) / 9 - 26
    longest = max(text_w(w, 1) for nm in names for w in str(nm).split()) * 1.04
    fs_nm = max(14.0, min(24 * k, inner / longest))
    cols = []
    for i in range(1, 10):
        if i == cur:
            cls = "cur"
        elif i == tgt:
            cls = "tgt"
        elif cur < i < tgt:
            cls = "path"
        elif i < cur:
            cls = "done"
        else:
            cls = ""
        tags = []
        if i == cur:
            tags.append('<span class="badge fill">현재</span>')
        if i == tgt:
            tags.append(f'<span class="badge hl">목표<br><span style="font-size:calc(17px*var(--k));font-weight:600">'
                        f'({esc(period)})</span></span>')
        tag = f'<div class="trl-tag">{"<br>".join(tags)}</div>' if tags else ""
        cols.append(f'<div class="trl-col">{tag}<div class="trl-step {cls}" style="min-height:{base_h + (i - 1) * step:.0f}px">'
                    f'<div class="n"><small>TRL</small>{i}</div><div class="nm" style="font-size:{fs_nm:.1f}px">'
                    f'{esc(names[i - 1])}</div></div></div>')
    head = (f'<div class="trl-head"><span class="track">TRL 구분: {esc(d.get("track", "공통"))}</span>'
            f'<span class="jump">현재 TRL {cur} → <em>목표 TRL {tgt}</em></span></div>')
    ev = (f'<div class="trl-ev"><span class="badge fill">현재 TRL {cur} 근거</span><div>{esc(d.get("evidence_current") or "[확보 필요]")}</div>'
          f'<span class="badge hl">목표 TRL {tgt} 검증</span><div>{esc(d.get("evidence_target") or "[확보 필요]")}</div></div>')
    return f'{head}<div class="trl">{"".join(cols)}</div><div class="trl-base"></div>{ev}'


# ───────────────────────── 5. gantt_milestones ─────────────────────────
def _assign_lane(lanes: list[list[tuple[int, int]]], a: int, b: int) -> int:
    """[a,b] 칸 구간이 겹치지 않는 첫 줄(lane) 번호(0부터)."""
    for i, occ in enumerate(lanes):
        if all(b < x or a > y for x, y in occ):
            occ.append((a, b))
            return i
    lanes.append([(a, b)])
    return len(lanes) - 1


def _gantt_timeline(bars, milestones, N, col_w, k, ctx: Ctx, row_name: str) -> str:
    fs = 22 * k
    bar_lanes: list[list[tuple[int, int]]] = []
    bar_items = []
    for bar in bars or []:
        try:
            a, b = int(bar.get("from")), int(bar.get("to"))
        except (TypeError, ValueError):
            raise ValueError(f"'{row_name}' 막대의 from/to가 숫자가 아닙니다")
        if a > b:
            a, b = b, a
        if a < 1 or b > N:
            ctx.warn(f"'{row_name}' 막대 {a}~{b}월이 표시 범위(1~{N})를 벗어나 잘랐습니다")
            a, b = max(1, a), min(N, b)
        label = str(bar.get("label") or "")
        bar_w = (b - a + 1) * col_w - 8
        lab_w = text_w(label, fs) + 24
        inside = (not label) or lab_w <= bar_w or ((b - a) >= 1 and lab_w <= 1.85 * bar_w)
        place, la, lb = "in", a, b
        if not inside:
            need = max(1, math.ceil((lab_w + 8) / col_w))
            if b + need <= N:
                place, la, lb = "right", b + 1, b + need
            elif a - need >= 1:
                place, la, lb = "left", a - need, a - 1
        occ_a, occ_b = min(a, la), max(b, lb)
        lane = _assign_lane(bar_lanes, occ_a, occ_b)
        bar_items.append((lane, a, b, label, place, la, lb))
    ms_lanes: list[list[tuple[int, int]]] = []
    ms_items = []
    for ms in milestones or []:
        try:
            m = int(ms.get("month"))
        except (TypeError, ValueError):
            raise ValueError(f"'{row_name}' 마일스톤 month가 숫자가 아닙니다")
        if not 1 <= m <= N:
            ctx.warn(f"'{row_name}' 마일스톤 {m}월이 표시 범위(1~{N}) 밖이라 뺐습니다")
            continue
        label = str(ms.get("label") or "")
        need = max(3, min(5, math.ceil((text_w(label, fs) / 2 + 24) / col_w)))
        need = min(need, N)
        a = m - (need - 1) // 2
        a = max(1, min(a, N - need + 1))
        b = a + need - 1
        lane = _assign_lane(ms_lanes, a, b)
        ms_items.append((lane, m, a, b, label))
    nb = max(1, len(bar_lanes)) if bar_items or not ms_items else 0
    R = nb + len(ms_lanes)
    out = [f'<div class="gt-glayer" data-nocheck style="position:absolute;inset:0;display:grid;'
           f'grid-template-columns:repeat({N},1fr)">'
           + "".join(f'<div class="gt-gl{" first" if i == 0 else ""}"></div>' for i in range(N)) + "</div>"]
    for lane, a, b, label, place, la, lb in bar_items:
        row = lane + 1
        if place == "in":
            out.append(f'<div class="gt-bar" style="grid-column:{a}/{b + 1};grid-row:{row}">{esc(label)}</div>')
        else:
            out.append(f'<div class="gt-bar short" style="grid-column:{a}/{b + 1};grid-row:{row}"></div>')
            out.append(f'<div class="gt-blab{" left" if place == "left" else ""}" style="grid-column:{la}/{lb + 1};'
                       f'grid-row:{row}">{esc(label)}</div>')
    for lane, m, a, b, label in ms_items:
        row = nb + lane + 1
        pos = ((m - a) + 0.5) / (b - a + 1) * 100
        al = "al-c" if (m - a) == (b - m) else ("al-l" if (m - a) < (b - m) else "al-r")
        out.append(f'<div class="gt-ms {al}" style="grid-column:{a}/{b + 1};grid-row:{row};--pos:{pos:.2f}%">'
                   f'<div class="dia"></div><div class="ml">{esc(label)}</div></div>')
    return (f'<div class="gt-tl" style="grid-template-rows:repeat({max(1, R)},auto)">{"".join(out)}</div>')


def b_gantt_milestones(d, ctx: Ctx) -> str:
    start = str(req(d, "start"))
    m0 = re.match(r"^(\d{4})[-./](\d{1,2})", start)
    if not m0:
        raise ValueError("data.start 는 'YYYY-MM' 형식이어야 합니다")
    y0, mo0 = int(m0.group(1)), int(m0.group(2))
    N = int(d.get("months") or 12)
    if not 1 <= N <= 36:
        raise ValueError("data.months 는 1~36 이어야 합니다")
    rows = req(d, "rows", list)
    k = ctx.k
    namew = int(ctx.width * 0.22)
    col_w = (ctx.width - namew) / N
    mh = []
    for i in range(N):
        mm = (mo0 - 1 + i) % 12 + 1
        yy = y0 + (mo0 - 1 + i) // 12
        ylab = str(yy) if (i == 0 or mm == 1) else "&nbsp;"
        mh.append(f'<div class="gt-mh{" first" if i == 0 else ""}"><span class="y">{ylab}</span>{mm}월</div>')
    parts = [f'<div class="gt-row head"><div class="gt-name">추진 내용</div><div class="gt-tl">{"".join(mh)}</div></div>']
    for r in rows:
        name = str(r.get("name") or "")
        tl = _gantt_timeline(r.get("bars"), r.get("milestones"), N, col_w, k, ctx, name)
        parts.append(f'<div class="gt-row"><div class="gt-name">{esc(name)}</div>{tl}</div>')
    hidden = d.get("hidden_schedule") or []
    if hidden:
        tl = _gantt_timeline([], hidden, N, col_w, k, ctx, "숨은 일정")
        parts.append(f'<div class="gt-row hidden"><div class="gt-name">숨은 일정(인증·허가)</div>{tl}</div>')
    road = ""
    if d.get("roadmap"):
        its = "".join(f'<div class="it"><b>{esc(x.get("period"))}</b>{esc(x.get("text"))}</div>' for x in d["roadmap"])
        road = f'<div class="gt-road"><div class="gt-name">이후 로드맵</div><div class="items">{its}</div></div>'
    legend = ('<div class="gt-legend"><span class="lg"><span class="sw-bar"></span>추진 기간</span>'
              '<span class="lg"><span class="sw-dia"></span>마일스톤(검증 지표)</span>'
              + ('<span class="lg"><span class="sw-bar" style="background:#EEF2F7;border-color:#1B3A5C"></span>숨은 일정: 인증·허가·시험 의뢰 등 외부 기관 일정</span>' if hidden else "")
              + "</div>")
    return (f'<div style="--namew:{namew}px;--months:{N}"><div class="gt">{"".join(parts)}</div>{road}{legend}</div>')


# ───────────────────────── 6. cost_table ─────────────────────────
def b_cost_table(d, ctx: Ctx) -> str:
    items = req(d, "items", list)
    rows = []
    s = 0.0
    sum_ok = True
    for it in items:
        amt = parse_krw(it.get("amount"))
        if amt is None:
            sum_ok = False
        else:
            s += amt
        q, u = first_number(it.get("qty")), parse_krw(it.get("unit_price"))
        if q is not None and u is not None and amt is not None and amt > 0 and abs(q * u - amt) / amt > 0.01:
            ctx.warn(f"'{it.get('name')}' 수량×단가({q:g}×{u:,.0f}={q * u:,.0f})가 금액({amt:,.0f})과 다릅니다")
        rows.append(f'<tr><td class="nm">{esc(it.get("name"))}</td><td class="num">{esc(it.get("qty"))}</td>'
                    f'<td class="num">{esc(it.get("unit_price"))}</td><td class="num">{esc(it.get("amount"))}</td>'
                    f'<td class="basis">{esc(it.get("basis"))}</td></tr>')
    total = d.get("total")
    tv = parse_krw(total)
    if total and sum_ok and tv and abs(tv - s) > 0.5:
        ctx.warn(f"항목 금액 합({s:,.0f}원)이 total({tv:,.0f}원)과 다릅니다")
    if total:
        rows.append(f'<tr class="total"><td colspan="3" class="ctr">합계</td><td class="num amt">{esc(total)}</td><td></td></tr>')
    table = ('<table class="t ct"><colgroup><col style="width:20%"><col style="width:10%"><col style="width:16%">'
             '<col style="width:18%"><col style="width:36%"></colgroup><thead><tr><th>항목</th><th>수량</th><th>단가</th>'
             f'<th>금액</th><th>산출 근거</th></tr></thead><tbody>{"".join(rows)}</tbody></table>')
    split = ""
    fs = d.get("funding_split") or []
    if fs:
        vals = [parse_krw(x.get("amount")) for x in fs]
        ok = all(v is not None and v > 0 for v in vals)
        tot = sum(vals) if ok else 0
        if ok and tv and abs(tot - tv) > 0.5:
            ctx.warn(f"분담 합계({tot:,.0f}원)가 total({tv:,.0f}원)과 다릅니다")
        segs, lgs = [], []
        for i, x in enumerate(fs):
            share = (vals[i] / tot) if ok and tot else 1 / len(fs)
            pct = fmt_pct(share) if ok else ""
            inner = pct if share >= 0.08 else ""
            segs.append(f'<div class="seg s{min(i, 3)}" style="width:{share * 100:.3f}%">{inner}</div>')
            lgs.append(f'<span><span class="sw seg s{min(i, 3)}" style="display:inline-block"></span>'
                       f'<b>{esc(x.get("label"))}</b> {esc(x.get("amount"))}{f" ({pct})" if pct else ""}</span>')
        split = (f'<div class="ct-split"><div class="bar" data-nocheck>{"".join(segs)}</div>'
                 f'<div class="lg">{"".join(lgs)}</div></div>')
    return table + split


# ───────────────────────── 7. team_org ─────────────────────────
def _org_card(m: dict, el: bool = False) -> str:
    role = str(m.get("role") or "")
    fill = " fill" if role.upper() == "EL" else ""
    return (f'<div class="org-card{" el" if el else ""}"><div class="hd"><span class="badge{fill}">{esc(role)}</span>'
            f'<span class="nm">{esc(m.get("name"))}</span></div>'
            + (f'<div class="af">{esc(m.get("affil"))}</div>' if m.get("affil") else "")
            + (f'<div class="ex">{esc(m.get("expertise"))}</div>' if m.get("expertise") else "")
            + (f'<div class="du">{esc(m.get("duty"))}</div>' if m.get("duty") else "")
            + "</div>")


def b_team_org(d, ctx: Ctx) -> str:
    members = req(d, "members", list)
    els = [m for m in members if str(m.get("role", "")).upper() == "EL"]
    if not els:
        ctx.warn("EL(대표·창업 리더) 역할이 없습니다")
    el = els[0] if els else None
    left = [m for m in members if str(m.get("role", "")).upper() == "PI"]
    right = [m for m in members if str(m.get("role", "")).upper() == "PM"]
    bottom = [m for m in members if m is not el and m not in left and m not in right]

    def side(ms):
        if not ms:
            return '<div class="org-side" style="visibility:hidden"></div><div class="org-link" style="visibility:hidden"></div>'
        return f'<div class="org-side">{"".join(_org_card(m) for m in ms)}</div><div class="org-link"></div>'

    if el:
        lft = side(left)
        rgt = side(right)
        # 오른쪽은 선→카드 순서
        rgt = rgt.replace('<div class="org-link"></div>', "").replace('<div class="org-link" style="visibility:hidden"></div>', "")
        rlink = '<div class="org-link"></div>' if right else '<div class="org-link" style="visibility:hidden"></div>'
        top = f'<div class="org-top">{lft}{_org_card(el, el=True)}{rlink}{rgt}</div>'
    else:
        top = f'<div class="org-top">{"".join(_org_card(m) for m in left + right)}</div>'
    bot = ""
    if bottom:
        n = len(bottom)
        its = "".join(f'<div class="ob-item{" first" if i == 0 else ""}{" last" if i == n - 1 else ""}"><div class="tick"></div>'
                      f'{_org_card(m)}</div>' for i, m in enumerate(bottom))
        bot = f'<div class="org-vline"></div><div class="org-bottom">{its}</div>'
    partners = ""
    if d.get("partners"):
        ps = d["partners"]
        its = "".join(f'<div class="p"><b>{esc(p.get("name"))}</b>{esc(p.get("role"))}</div>' for p in ps)
        partners = (f'<div class="org-partners" style="--pcols:{min(4, len(ps))}"><div class="lab">협력 기관</div>'
                    f'<div class="list">{its}</div></div>')
    return top + bot + partners


# ───────────────────────── 8·9. evidence_card / evidence_board ─────────────────────────
def _ev_block(it: dict, ctx: Ctx, board: bool) -> str:
    uri = resolve_image(it.get("image"), ctx)
    if not it.get("image"):
        ctx.warn(f"{it.get('label') or '증거'}: 이미지가 지정되지 않아 '[이미지 확보 필요]'로 표시했습니다")
    if uri:
        img = f'<div class="ev-img"><img src="{uri}" alt=""></div>'
    else:
        img = '<div class="ev-missing">[이미지 확보 필요]</div>'
    lab = f'<div class="ev-top"><span class="badge fill">{esc(it.get("label"))}</span></div>' if it.get("label") else ""
    return (f'<div class="ev-card">{lab}{img}'
            + (f'<div class="ev-cap">{esc(it.get("caption"))}</div>' if it.get("caption") else "")
            + (f'<div class="ev-proves">{esc(it.get("proves"))}</div>' if it.get("proves") else "")
            + (f'<div class="ev-src">{esc(it.get("source"))}</div>' if it.get("source") else "")
            + "</div>")


def b_evidence_card(d, ctx: Ctx) -> str:
    if not isinstance(d, dict) or not (d.get("caption") or d.get("image")):
        raise ValueError("data.image 또는 data.caption 이 필요합니다")
    return (f'<div class="ev-single" style="--imgmax:{900 * 1:.0f}px;--imgbox:400px">'
            '<style>.ev-single .ev-img img{width:100%;height:auto;max-height:var(--imgmax);object-fit:contain}</style>'
            f'{_ev_block(d, ctx, board=False)}</div>')


def b_evidence_board(d, ctx: Ctx) -> str:
    items = req(d, "items", list)
    n = len(items)
    cols = 3 if n in (3, 5, 6) or n > 6 else 2
    if n == 1:
        cols = 1
    box = {1: 700, 2: 460, 3: 320}[cols]
    return (f'<div class="ev-board" style="--cols:{cols};--imgbox:{box}px">'
            '<style>.ev-board .ev-img img{width:100%;height:100%;object-fit:contain}</style>'
            + "".join(_ev_block(it, ctx, board=True) for it in items) + "</div>")


# ───────────────────────── 10. kpi_strip ─────────────────────────
def b_kpi_strip(d, ctx: Ctx) -> str:
    items = req(d, "items", list)
    n = len(items)
    if not 1 <= n <= 5:
        ctx.warn(f"kpi_strip 항목은 3~4개를 권장합니다(현재 {n}개)")
    k = ctx.k
    col_w = ctx.width / max(1, n) - 64
    its = []
    for it in items:
        val, unit = str(it.get("value", "")), str(it.get("unit", ""))
        need = text_w(val, 56 * k) + text_w(unit, 28 * k) + 8
        fs = 56 * k if need <= col_w else max(36 * k, 56 * k * col_w / need)
        us = 28 * k * fs / (56 * k)
        hl = " hl" if it.get("highlight") else ""
        its.append(f'<div class="it{hl}"><div class="v" style="font-size:{fs:.1f}px">{esc(val)}'
                   f'<small style="font-size:{us:.1f}px">{esc(unit)}</small></div>'
                   f'<div class="lb">{esc(it.get("label"))}</div>'
                   + (f'<div class="sr">{esc(it.get("source"))}</div>' if it.get("source") else "") + "</div>")
    return f'<div class="kpi" style="--cols:{n}">{"".join(its)}</div>'


# ───────────────────────── 11. prototype_stages ─────────────────────────
def b_prototype_stages(d, ctx: Ctx) -> str:
    st = req(d, "stages", list)
    n = len(st)
    chev, body, trl = [], [], []
    for i, s in enumerate(st):
        cur = " cur" if s.get("current") else ""
        first = " first" if i == 0 else ""
        col = i + 1
        chev.append(f'<div class="ps-chev{first}{cur}" style="grid-column:{col};grid-row:1"><div><span class="st">{i + 1}단계</span>'
                    f'{esc(s.get("name"))}</div></div>')
        body.append(f'<div class="ps-body{cur}" style="grid-column:{col};grid-row:2/span 3">'
                    f'<div class="row"><span class="k">무엇을 만드나</span><div class="v">{esc(s.get("what"))}</div></div>'
                    f'<div class="row"><span class="k">무엇을 확인하나</span><div class="v">{esc(s.get("verifies"))}</div></div>'
                    f'<div class="row succ"><span class="k">성공 기준</span><div class="v">{esc(s.get("success"))}</div></div></div>')
        t = s.get("trl")
        badge = f'<span class="badge{" fill" if cur else ""}">TRL {esc(t)}</span>' if t not in (None, "") else ""
        if cur:
            badge += ' <span class="badge hl" style="font-size:var(--fs-cap)">현재 단계</span>'
        trl.append(f'<div class="ps-trl" style="grid-column:{col};grid-row:5">{badge}</div>')
    return f'<div class="ps" style="--cols:{n}">{"".join(chev)}{"".join(body)}{"".join(trl)}</div>'


# ───────────────────────── 12(보너스). customer_profile ─────────────────────────
CP_ROWS = [("who", "누구인가"), ("situation", "어떤 상황"), ("pain", "핵심 불편"), ("current_alt", "지금의 대안"), ("wtp", "지불 의향")]


def b_customer_profile(d, ctx: Ctx) -> str:
    cards = []
    for key, title, sub in (("primary", "1차 고객", "핵심 타깃"), ("secondary", "2차 고객", "확장 타깃")):
        p = d.get(key)
        if not p:
            if key == "primary":
                raise ValueError("data.primary 가 없습니다")
            continue
        rows = "".join(f'<div class="k">{lab}</div><div class="v{" wtp" if f == "wtp" else ""}">{esc(p.get(f) or "[확보 필요]")}</div>'
                       for f, lab in CP_ROWS)
        cards.append(f'<div class="cp-card {key}"><div class="cp-hd">{title}<small>{sub}</small></div>{rows}</div>')
    style = '' if len(cards) == 2 else ' style="grid-template-columns:1fr"'
    return f'<div class="cp"{style}>{"".join(cards)}</div>'


BUILDERS = {
    "competitor_matrix": b_competitor_matrix,
    "tam_sam_som": b_tam_sam_som,
    "tech_concept": b_tech_concept,
    "trl_ladder": b_trl_ladder,
    "gantt_milestones": b_gantt_milestones,
    "cost_table": b_cost_table,
    "team_org": b_team_org,
    "evidence_card": b_evidence_card,
    "evidence_board": b_evidence_board,
    "kpi_strip": b_kpi_strip,
    "prototype_stages": b_prototype_stages,
    "customer_profile": b_customer_profile,
}
SUPPORTED_TYPES = list(BUILDERS)


# ───────────────────────── 렌더링 ─────────────────────────
def build_page(fig: dict, ctx: Ctx, body: str) -> str:
    """빌더가 만든 본문을 공통 CSS·라벨·고지·측정 스크립트와 함께 완전한 HTML로 감싼다."""
    css = CSS_PATH.read_text(encoding="utf-8")
    title = f'<div class="fig-title">{esc(fig.get("title"))}</div>' if fig.get("title") else ""
    notice = f'<div class="fig-notice">{esc(fig.get("notice"))}</div>' if fig.get("notice") else ""
    return (f'<!doctype html><html lang="ko" style="--w:{ctx.width}px;--k:{ctx.k}"><head><meta charset="utf-8">'
            f'<style>{css}</style></head><body><div class="fig fig-{esc(fig.get("type"))}">{title}{body}{notice}</div>'
            f'<script>{METRICS_JS}</script></body></html>')


def _chrome(args: list[str], timeout: int = 90) -> tuple[str, str]:
    """Chrome 헤드리스 1회 실행(호출마다 새 프로필 폴더 — 병렬 실행 시 프로필 잠금 방지)."""
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError("Chrome/Edge를 찾지 못했습니다 — 설치 후 다시 시도")
    prof = tempfile.mkdtemp(prefix="texcore_fig_chrome_")
    base = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
            "--disable-extensions", "--run-all-compositor-stages-before-draw", f"--user-data-dir={prof}", "--lang=ko-KR"]
    try:
        r = subprocess.run(base + args, capture_output=True, timeout=timeout)
        return r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
    finally:
        shutil.rmtree(prof, ignore_errors=True)


def _metrics(dom: str) -> dict:
    m = re.search(r'data-metrics="([^"]*)"', dom)
    if not m:
        return {}
    try:
        return json.loads(html.unescape(m.group(1)))
    except ValueError:
        return {}


def _trim(im: Image.Image, pad: int) -> tuple[Image.Image, tuple, float]:
    """순백 여백을 잘라내고 pad만큼 흰 여백을 남긴다. (결과, 원본 bbox, 잉크 비율)"""
    rgb = im.convert("RGB")
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, (255, 255, 255))).convert("L")
    mask = diff.point(lambda p: 255 if p > 8 else 0)
    bbox = mask.getbbox()
    if not bbox:
        raise RuntimeError("렌더 결과가 순백입니다(내용 없음)")
    l, t, r, b = bbox
    W, H = r - l + 2 * pad, b - t + 2 * pad
    out = Image.new("RGB", (W, H), (255, 255, 255))
    out.paste(rgb.crop(bbox), (pad, pad))
    hist = mask.crop(bbox).histogram()
    ink = hist[255] / max(1, (r - l) * (b - t))
    return out, bbox, ink


def render_html(doc: str, out_png, width_css: int, scale: float = DEFAULT_SCALE, keep_html: bool = False) -> dict:
    """완성 HTML 문자열 → 트리밍된 PNG. 반환: {w, h, warnings, ink}"""
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="texcore_fig_"))
    warnings: list[str] = []
    try:
        src = tmp / "fig.html"
        src.write_text(doc, encoding="utf-8")
        if keep_html:
            shutil.copyfile(src, out_png.with_suffix(".html"))
        shot = tmp / "shot.png"
        win_w = int(width_css) + 2 * BODY_PAD
        height = FIRST_HEIGHT
        met: dict = {}
        for attempt in range(3):
            if shot.exists():
                shot.unlink()
            dom, err = _chrome([f"--force-device-scale-factor={scale:g}", f"--window-size={win_w},{height}",
                                "--virtual-time-budget=3000", f"--screenshot={shot}", "--dump-dom", src.as_uri()])
            if not shot.exists():
                raise RuntimeError("스크린샷 실패: " + err.strip()[-300:])
            met = _metrics(dom)
            need = (met.get("bottom") or 0) + BODY_PAD + 16
            if met and need > height and attempt < 2:
                height = int(need + 200)   # 그림이 창보다 길다 → 실측 높이로 다시 촬영
                continue
            break
        if not met:
            warnings.append("페이지 측정값을 읽지 못했습니다(넘침 검사 생략)")
        warnings += met.get("issues") or []
        im = Image.open(shot)
        im.load()
        pad = int(round(TRIM_PAD * scale))
        out, bbox, ink = _trim(im, pad)
        if bbox[3] >= im.height - 1 or bbox[2] >= im.width - 1:
            warnings.append("내용이 촬영 창 가장자리에 닿음 — 잘렸을 수 있음")
        dpi = scale * DEFAULT_WIDTH / (DOC_MM_PER_1600 / 25.4)
        out.save(out_png, "PNG", dpi=(dpi, dpi), optimize=True)
        return {"w": out.width, "h": out.height, "warnings": warnings, "ink": round(ink, 4)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _safe_id(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", str(s)).strip("._")
    return s or "figure"


def render_one(fig: dict, out_dir, base_dir=None, scale: float = DEFAULT_SCALE, keep_html: bool = False) -> dict:
    """그림 1개 렌더. 실패해도 예외를 던지지 않고 ok=False·error로 돌려준다."""
    res = {"id": fig.get("id"), "type": fig.get("type"), "file": None, "w": 0, "h": 0, "ok": False, "error": None,
           "warnings": [], "ink": 0.0}
    try:
        if not fig.get("id"):
            raise ValueError("id 가 없습니다")
        typ = fig.get("type")
        builder = BUILDERS.get(typ)
        if not builder:
            raise ValueError(f"지원하지 않는 유형입니다: {typ} (지원: {', '.join(SUPPORTED_TYPES)})")
        width = int(fig.get("width_px") or DEFAULT_WIDTH)
        if not 400 <= width <= 4000:
            raise ValueError("width_px 는 400~4000 이어야 합니다")
        k = float(fig.get("font_scale") or 1.0)
        if not 0.5 <= k <= 3:
            raise ValueError("font_scale 은 0.5~3.0 이어야 합니다")
        ctx = Ctx(width, k, base_dir)
        body = builder(fig.get("data") or {}, ctx)
        doc = build_page(fig, ctx, body)
        out_png = Path(out_dir) / f"{_safe_id(fig['id'])}.png"
        info = render_html(doc, out_png, width, scale, keep_html)
        res.update(file=out_png.name, path=str(out_png), w=info["w"], h=info["h"], ok=True, ink=info["ink"],
                   warnings=ctx.warnings + info["warnings"])
        if info["ink"] < 0.005:
            res["warnings"].append(f"잉크 비율이 매우 낮음({info['ink']:.3%}) — 내용이 비었을 수 있음")
    except Exception as ex:  # noqa: BLE001 — 그림 하나 실패가 전체를 멈추지 않게
        res["error"] = f"{type(ex).__name__}: {ex}"
    return res


def render_all(spec, out_dir, scale: float = DEFAULT_SCALE, only: list[str] | None = None,
               keep_html: bool = False, jobs: int = 3) -> list[dict]:
    """spec(dict 또는 JSON 경로)의 모든 그림을 렌더하고 out_dir/figures_report.json 을 쓴다."""
    if isinstance(spec, (str, Path)):
        p = Path(spec)
        base = p.resolve().parent
        spec = json.loads(p.read_text(encoding="utf-8"))
    else:
        base = Path(spec.get("base_dir") or Path.cwd())
    figs = spec.get("figures") or []
    if only:
        figs = [f for f in figs if f.get("id") in only]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        results = list(ex.map(lambda f: render_one(f, out, base, scale, keep_html), figs))
    report = [{k: v for k, v in r.items() if k != "path"} for r in results]
    (out / "figures_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="텍스코어 사업신청서 시각자료(PNG) 생성기")
    ap.add_argument("--spec", required=True, help="그림 스펙 JSON 경로")
    ap.add_argument("--out", required=True, help="PNG·figures_report.json 출력 폴더")
    ap.add_argument("--scale", type=float, default=DEFAULT_SCALE, help="장치 배율(기본 2 = 고해상도)")
    ap.add_argument("--only", help="쉼표로 구분한 id만 렌더")
    ap.add_argument("--keep-html", action="store_true", help="디버그용 {id}.html 도 저장")
    ap.add_argument("--jobs", type=int, default=3, help="동시 렌더 개수(기본 3)")
    a = ap.parse_args(argv)
    only = [s.strip() for s in a.only.split(",")] if a.only else None
    results = render_all(a.spec, a.out, a.scale, only, a.keep_html, a.jobs)
    n_ok = sum(1 for r in results if r["ok"])
    for r in results:
        if r["ok"]:
            print(f"[성공] {r['id']} ({r['type']}) → {r['file']} {r['w']}x{r['h']}"
                  + (f"  경고 {len(r['warnings'])}건" if r["warnings"] else ""))
            for w in r["warnings"]:
                print(f"       - {w}")
        else:
            print(f"[실패] {r['id']} ({r['type']}): {r['error']}")
    print(f"완료: 성공 {n_ok} / 전체 {len(results)} → {Path(a.out) / 'figures_report.json'}")
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
