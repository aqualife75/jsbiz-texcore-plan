# -*- coding: utf-8 -*-
from __future__ import annotations
import io
from pathlib import Path
import fitz
from PIL import Image
from .images import save_image

MAX_PAGE_RENDER = 30

def extract(path, out_dir) -> dict:
    path = Path(path); out_dir = Path(out_dir)
    doc = fitz.open(str(path))
    texts, images, warnings = [], [], []
    stem = path.stem[:40]
    k = 0
    for pno, page in enumerate(doc, 1):
        texts.append(f"\n--- p{pno} ---\n" + page.get_text("text"))
        for info in page.get_images(full=True):
            try:
                pix = doc.extract_image(info[0])
                im = Image.open(io.BytesIO(pix["image"])); im.load()
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"p{pno} image xref {info[0]}: {exc}"); continue
            k += 1
            rec = save_image(im, out_dir, stem, k, f"{path.name}:p{pno}")
            if rec: images.append(rec)
        if pno <= MAX_PAGE_RENDER:
            pm = page.get_pixmap(dpi=100)
            dst = out_dir / f"{stem}_page{pno:02d}.png"; out_dir.mkdir(parents=True, exist_ok=True)
            pm.save(str(dst))
            images.append({"file": str(dst), "origin": f"{path.name}:page{pno}", "w": pm.width, "h": pm.height, "page_render": True})
    if len(doc) > MAX_PAGE_RENDER:
        warnings.append(f"page render limited to {MAX_PAGE_RENDER} of {len(doc)} pages")
    return {"text": "".join(texts), "images": images, "warnings": warnings}
