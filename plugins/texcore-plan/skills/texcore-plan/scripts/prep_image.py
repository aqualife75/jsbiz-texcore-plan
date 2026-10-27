# -*- coding: utf-8 -*-
"""이미지 전처리: PNG 변환·커버 맞춤·어둡게·라운딩·크롭. 빌더와 에이전트가 CLI/함수로 사용."""
from __future__ import annotations
import argparse, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps

def _open(p) -> Image.Image:
    im = Image.open(p); im.load(); return ImageOps.exif_transpose(im)

def to_png(src, dst):
    im = _open(src); (im.convert("RGBA") if im.mode in ("P", "LA", "CMYK") else im).save(dst, "PNG"); return dst

def fit_cover(src, dst, w_px: int, h_px: int):
    im = _open(src).convert("RGB")
    im = ImageOps.fit(im, (int(w_px), int(h_px)), method=Image.LANCZOS, centering=(0.5, 0.5))
    im.save(dst, "PNG"); return dst

def darken(src, dst, strength: float = 0.6, tint: str = "10141B"):
    im = _open(src).convert("RGBA")
    r, g, b = int(tint[0:2], 16), int(tint[2:4], 16), int(tint[4:6], 16)
    overlay = Image.new("RGBA", im.size, (r, g, b, int(255 * max(0.0, min(1.0, strength)))))
    Image.alpha_composite(im, overlay).convert("RGB").save(dst, "PNG"); return dst

def round_corners(src, dst, radius_px: int = 24):
    im = _open(src).convert("RGBA")
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=radius_px, fill=255)
    im.putalpha(mask); im.save(dst, "PNG"); return dst

def crop(src, dst, box):
    im = _open(src); im.crop(tuple(int(v) for v in box)).save(dst, "PNG"); return dst

def panel(src, dst, w_px: int, h_px: int, strength: float = 0.6):
    fit_cover(src, dst, w_px, h_px); return darken(dst, dst, strength)

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="prep_image.py")
    sub = ap.add_subparsers(dest="op", required=True)
    for op in ("to_png", "fit_cover", "darken", "round", "crop", "panel"):
        p = sub.add_parser(op); p.add_argument("src"); p.add_argument("dst")
        if op in ("fit_cover", "panel"): p.add_argument("--size", default="1440x1080", help="WxH px")
        if op in ("darken", "panel"): p.add_argument("--strength", type=float, default=0.6)
        if op == "round": p.add_argument("--radius", type=int, default=24)
        if op == "crop": p.add_argument("--box", required=True, help="l,t,r,b px")
    a = ap.parse_args(argv)
    if a.op == "to_png": to_png(a.src, a.dst)
    elif a.op == "fit_cover": w, h = a.size.lower().split("x"); fit_cover(a.src, a.dst, int(w), int(h))
    elif a.op == "darken": darken(a.src, a.dst, a.strength)
    elif a.op == "round": round_corners(a.src, a.dst, a.radius)
    elif a.op == "crop": crop(a.src, a.dst, [int(v) for v in a.box.split(",")])
    elif a.op == "panel": w, h = a.size.lower().split("x"); panel(a.src, a.dst, int(w), int(h), a.strength)
    print(a.dst); return 0

if __name__ == "__main__":
    sys.exit(main())
