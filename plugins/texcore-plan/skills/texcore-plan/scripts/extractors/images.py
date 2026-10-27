# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageOps

MAX_SIDE = 2400
MIN_PX = 40

def save_image(im: Image.Image, out_dir: Path, stem: str, n: int, origin: str, prefer_jpg=False) -> dict | None:
    """PIL 이미지를 정규화해 저장. 너무 작으면 None."""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    im = ImageOps.exif_transpose(im)
    if im.width < MIN_PX or im.height < MIN_PX:
        return None
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE))
    if prefer_jpg and im.mode == "RGB":
        dst = out_dir / f"{stem}_{n:02d}.jpg"; im.save(dst, "JPEG", quality=92)
    else:
        dst = out_dir / f"{stem}_{n:02d}.png"
        (im.convert("RGBA") if im.mode in ("P", "LA", "CMYK") else im).save(dst, "PNG")
    return {"file": str(dst), "origin": origin, "w": im.width, "h": im.height}

def extract(path, out_dir) -> dict:
    path = Path(path)
    try:
        im = Image.open(path); im.load()
    except Exception as exc:  # noqa: BLE001
        return {"text": "", "images": [], "warnings": [f"unreadable image {path.name}: {exc}"]}
    rec = save_image(im, Path(out_dir), path.stem[:40], 1, path.name, prefer_jpg=(path.suffix.lower() in (".jpg", ".jpeg")))
    return {"text": "", "images": [rec] if rec else [], "warnings": [] if rec else [f"tiny image {path.name}"]}
