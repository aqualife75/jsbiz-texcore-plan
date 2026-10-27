# -*- coding: utf-8 -*-
"""make_figures 테스트용 '설명용 샘플' 증거 이미지 3장을 만든다(가상 데이터).

사용: python -X utf8 scripts/make_sample_assets.py   → tests/fixtures/sample_assets/*.png
실제 사진·시험성적서가 아니며, 이미지 안에 '설명용 샘플' 문구를 넣는다.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "texcore-plan" / "skills" / "texcore-plan" / "scripts"))
import make_figures as mf  # noqa: E402

OUT = ROOT / "tests" / "fixtures" / "sample_assets"

BASE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
body{margin:0;padding:24px;background:#fff;font-family:'Pretendard','Malgun Gothic',sans-serif;color:#1E293B;word-break:keep-all}
.fig{width:%dpx}.tag{position:absolute;top:16px;right:16px;background:#DC2626;color:#fff;font-weight:700;font-size:20px;padding:4px 12px;border-radius:4px}
</style></head><body><div class="fig" style="position:relative">%s</div></body></html>"""

PROTO = """
<div style="background:#E9EEF4;height:640px;border-radius:8px;position:relative;overflow:hidden">
 <span class="tag">설명용 샘플 이미지</span>
 <svg viewBox="0 0 960 640" width="960" height="640">
  <rect x="0" y="520" width="960" height="120" fill="#CBD5E1"/>
  <circle cx="420" cy="400" r="190" fill="none" stroke="#334155" stroke-width="18"/>
  <circle cx="420" cy="400" r="150" fill="none" stroke="#64748B" stroke-width="6"/>
  <circle cx="420" cy="400" r="22" fill="#334155"/>
  <rect x="300" y="150" width="300" height="40" rx="10" fill="#475569"/>
  <rect x="560" y="150" width="30" height="260" fill="#475569"/>
  <circle cx="720" cy="520" r="60" fill="none" stroke="#334155" stroke-width="14"/>
  <rect x="380" y="330" width="170" height="130" rx="14" fill="#1B3A5C"/>
  <rect x="400" y="350" width="60" height="18" rx="4" fill="#DC2626"/>
  <text x="465" y="420" fill="#fff" font-size="26" font-family="Pretendard, Malgun Gothic" text-anchor="middle">보조 구동</text>
  <line x1="550" y1="395" x2="700" y2="300" stroke="#DC2626" stroke-width="4" stroke-dasharray="10 8"/>
  <text x="705" y="290" fill="#1E293B" font-size="28" font-weight="700" font-family="Pretendard, Malgun Gothic">원클릭 장착 브래킷</text>
 </svg>
 <div style="position:absolute;left:24px;bottom:20px;font-size:22px;color:#334155">시제품 사진 자리 · 가상 일러스트</div>
</div>"""

REPORT = """
<div style="border:2px solid #1E293B;padding:40px 48px;position:relative">
 <span class="tag">설명용 샘플</span>
 <div style="text-align:center;font-size:40px;font-weight:800;letter-spacing:0.2em">시 험 결 과 표</div>
 <div style="text-align:center;font-size:20px;color:#64748B;margin-top:8px">OO대학교 재활공학연구실 · 기록번호 SAMPLE-2026-015 (가상)</div>
 <table style="width:100%;border-collapse:collapse;margin-top:32px;font-size:24px">
  <tr style="background:#EEF2F7"><th style="border:1px solid #94A3B8;padding:12px">시험 항목</th><th style="border:1px solid #94A3B8;padding:12px">조건</th><th style="border:1px solid #94A3B8;padding:12px">횟수</th><th style="border:1px solid #94A3B8;padding:12px">결과</th></tr>
  <tr><td style="border:1px solid #94A3B8;padding:12px">경사 등판</td><td style="border:1px solid #94A3B8;padding:12px">10° 경사로, 체중 70kg</td><td style="border:1px solid #94A3B8;padding:12px;text-align:center">20</td><td style="border:1px solid #94A3B8;padding:12px;text-align:center">20/20 성공</td></tr>
  <tr><td style="border:1px solid #94A3B8;padding:12px">경사 정지(밀림)</td><td style="border:1px solid #94A3B8;padding:12px">15° 경사로, 손 뗌</td><td style="border:1px solid #94A3B8;padding:12px;text-align:center">20</td><td style="border:1px solid #94A3B8;padding:12px;text-align:center;color:#DC2626;font-weight:700">밀림 0건</td></tr>
  <tr><td style="border:1px solid #94A3B8;padding:12px">장착 시간</td><td style="border:1px solid #94A3B8;padding:12px">공구 없이, 비숙련자</td><td style="border:1px solid #94A3B8;padding:12px;text-align:center">5</td><td style="border:1px solid #94A3B8;padding:12px;text-align:center">평균 4분 40초</td></tr>
 </table>
 <div style="margin-top:28px;font-size:20px;color:#64748B">※ 본 표는 시각자료 생성기 시험용 가상 데이터입니다.</div>
</div>"""

CHART = """
<div style="border:1px solid #CBD5E1;padding:32px 40px;position:relative">
 <span class="tag">설명용 샘플</span>
 <div style="font-size:30px;font-weight:800">"50만 원 이하라면 사겠다" 응답</div>
 <div style="font-size:20px;color:#64748B;margin-top:4px">수동 휠체어 사용자 인터뷰 n=20 · 가상 데이터</div>
 <div style="margin-top:28px;display:grid;grid-template-columns:200px 1fr 80px;gap:16px 16px;align-items:center;font-size:24px">
  <div>바로 구매</div><div style="background:#1B3A5C;height:40px;width:40%"></div><div><b>8명</b></div>
  <div>조건부 구매</div><div style="background:#1B3A5C;height:40px;width:30%"></div><div><b>6명</b></div>
  <div>보류</div><div style="background:#CBD5E1;height:40px;width:20%"></div><div>4명</div>
  <div>구매 안 함</div><div style="background:#CBD5E1;height:40px;width:10%"></div><div>2명</div>
 </div>
 <div style="margin-top:24px;font-size:22px;color:#DC2626;font-weight:700">구매 의향 14/20명 (70%)</div>
</div>"""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, w, body in (("proto_photo.png", 960, PROTO), ("test_report.png", 1000, REPORT), ("interview_chart.png", 900, CHART)):
        info = mf.render_html(BASE % (w, body), OUT / name, w, scale=1.5)
        print(name, info["w"], "x", info["h"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
