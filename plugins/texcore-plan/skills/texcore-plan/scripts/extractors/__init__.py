# -*- coding: utf-8 -*-
"""입력 파일 → {"kind","text","images","warnings"}. 확장자별 디스패치."""
from __future__ import annotations
from pathlib import Path
from . import hwp, hwpx, pdf, docx, pptx, xlsx, images
from .images import save_image  # re-export

_MAP = {
    ".hwp": ("hwp", hwp.extract), ".hwpx": ("hwpx", hwpx.extract), ".pdf": ("pdf", pdf.extract),
    ".docx": ("docx", docx.extract), ".pptx": ("pptx", pptx.extract), ".xlsx": ("xlsx", xlsx.extract),
    ".png": ("image", images.extract), ".jpg": ("image", images.extract), ".jpeg": ("image", images.extract),
    ".bmp": ("image", images.extract), ".gif": ("image", images.extract), ".webp": ("image", images.extract),
}
SUPPORTED = set(_MAP) | {".md", ".txt", ".csv"}

def extract_file(path, out_dir) -> dict:
    path = Path(path); ext = path.suffix.lower()
    if ext in (".md", ".txt", ".csv"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            return {"kind": "text", "text": "", "images": [], "warnings": [f"read failed {path.name}: {exc}"]}
        return {"kind": "text", "text": text, "images": [], "warnings": []}
    if ext not in _MAP:
        return {"kind": "unsupported", "text": "", "images": [], "warnings": [f"unsupported extension {ext}: {path.name}"]}
    kind, fn = _MAP[ext]
    try:
        res = fn(path, Path(out_dir))
    except Exception as exc:  # noqa: BLE001
        return {"kind": kind, "text": "", "images": [], "warnings": [f"extract failed {path.name}: {exc}"]}
    res["kind"] = kind
    return res
