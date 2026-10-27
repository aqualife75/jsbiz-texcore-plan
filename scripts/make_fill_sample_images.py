# -*- coding: utf-8 -*-
"""주입 엔진 테스트용 샘플 그림 3장(PIL) — 모두 '설명용 샘플' 표기.

python -X utf8 scripts/make_fill_sample_images.py   →  tests/fixtures/fill_sample_img/*.png
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures" / "fill_sample_img"


def font(size, bold=False):
    cands = (["malgunbd.ttf"] if bold else []) + ["malgun.ttf", "AppleSDGothicNeo.ttc", "NanumGothic.ttf"]
    for name in cands:
        for base in (Path("C:/Windows/Fonts"), Path("/System/Library/Fonts"), Path("/Library/Fonts")):
            p = base / name
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def stamp(d: ImageDraw.ImageDraw, w, h):
    f = font(30, True)
    txt = "설명용 샘플"
    tw = d.textlength(txt, font=f)
    d.rounded_rectangle([w - tw - 50, 18, w - 18, 70], radius=10, fill=(220, 38, 38))
    d.text((w - tw - 34, 24), txt, font=f, fill="white")


def prototype():
    w, h = 1600, 1000
    im = Image.new("RGB", (w, h), (246, 248, 251))
    d = ImageDraw.Draw(im)
    d.text((60, 40), "1차 시제품 형상(모터 하우징 부착형)", font=font(46, True), fill=(15, 23, 42))
    d.rounded_rectangle([180, 260, 900, 760], radius=40, fill=(71, 85, 105))          # 모터
    d.ellipse([820, 380, 1060, 640], fill=(100, 116, 139))
    d.rectangle([1060, 480, 1300, 540], fill=(148, 163, 184))                          # 축
    d.rounded_rectangle([380, 170, 700, 290], radius=18, fill=(37, 99, 235))           # 센서 모듈
    d.text((420, 200), "압전 센서 모듈", font=font(36, True), fill="white")
    d.line([540, 290, 540, 330], fill=(37, 99, 235), width=8)
    for i, (lbl, y) in enumerate([("① 압전 박막(두께 52㎛)", 820), ("② 저전력 MCU·BLE", 880), ("③ 마그넷 부착 하우징", 940)]):
        d.text((180, y - 30), lbl, font=font(34), fill=(30, 41, 59))
    d.text((1120, 300), "크기 38×38×12mm", font=font(34), fill=(30, 41, 59))
    d.text((1120, 350), "배터리 18개월(목표)", font=font(34), fill=(30, 41, 59))
    stamp(d, w, h)
    return im, "sample_prototype.png"


def chart():
    w, h = 1300, 1000
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    d.text((60, 40), "베어링 상태별 진동 진폭(RMS, n=40)", font=font(44, True), fill=(15, 23, 42))
    base, left = 860, 170
    d.line([left, 160, left, base], fill=(100, 116, 139), width=4)
    d.line([left, base, w - 80, base], fill=(100, 116, 139), width=4)
    data = [("정상", 1.0, (148, 163, 184)), ("초기 결함", 2.6, (96, 165, 250)), ("진행 결함", 4.2, (37, 99, 235))]
    bw = 220
    for i, (lbl, v, col) in enumerate(data):
        x0 = left + 90 + i * 340
        top = base - int(v * 150)
        d.rectangle([x0, top, x0 + bw, base], fill=col)
        d.text((x0 + 60, top - 60), f"×{v:.1f}", font=font(40, True), fill=(15, 23, 42))
        d.text((x0 + 40, base + 20), lbl, font=font(36), fill=(30, 41, 59))
    stamp(d, w, h)
    return im, "sample_chart.png"


def interview():
    w, h = 1600, 900
    im = Image.new("RGB", (w, h), (255, 251, 235))
    d = ImageDraw.Draw(im)
    d.text((60, 40), "현장 인터뷰 32건 — 반복된 문제 TOP3", font=font(46, True), fill=(15, 23, 42))
    rows = [("돌발 정지 후 원인 파악에 반나절 이상", 27), ("점검 인력 1명이 설비 120대 담당", 22), ("기존 진단 장비 1대 900만 원 — 소형 모터엔 과함", 19)]
    for i, (lbl, n) in enumerate(rows):
        y = 200 + i * 210
        d.text((60, y), lbl, font=font(38), fill=(30, 41, 59))
        d.rounded_rectangle([60, y + 70, 60 + n * 40, y + 130], radius=12, fill=(245, 158, 11))
        d.text((80 + n * 40, y + 72), f"{n}/32명", font=font(38, True), fill=(120, 53, 15))
    stamp(d, w, h)
    return im, "sample_interview.png"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in (prototype, chart, interview):
        im, name = fn()
        im.save(OUT / name, dpi=(150, 150))
        print(OUT / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
