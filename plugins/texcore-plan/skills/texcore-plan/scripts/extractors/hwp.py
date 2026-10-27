# -*- coding: utf-8 -*-
"""HWP 5.0 (OLE 복합문서) → 본문 텍스트 + BinData 이미지.

- 텍스트: BodyText/Section* 스트림을 zlib raw-deflate 해제 후 HWPTAG_PARA_TEXT(67) 레코드 복원.
- 이미지: BinData/* 스트림. 매직 바이트로 형식 판별, 아니면 zlib 해제 후 재판별. BMP/GIF/TIF → PNG 변환.
- 표는 셀 텍스트가 문단 순서로 나열됨(구조 미복원). 40px 미만 이미지는 아이콘으로 보고 건너뜀.
"""
from __future__ import annotations
import io, struct, zlib
from pathlib import Path

import olefile
from PIL import Image

from .images import save_image

HWPTAG_PARA_TEXT = 67
_EXTENDED_CTRL = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}


def decode_para_text(payload: bytes) -> str:
    chars: list[str] = []
    j, n = 0, len(payload) - 1
    while j < n:
        c = struct.unpack("<H", payload[j:j + 2])[0]
        if c == 0:
            j += 2
        elif c in (10, 13):
            chars.append("\n"); j += 2
        elif c < 32:
            j += 16 if c in _EXTENDED_CTRL else 2
            chars.append(" ")
        elif 0xD800 <= c <= 0xDBFF:
            if j + 4 <= len(payload):
                c2 = struct.unpack("<H", payload[j + 2:j + 4])[0]
                if 0xDC00 <= c2 <= 0xDFFF:
                    chars.append(chr(0x10000 + ((c - 0xD800) << 10) + (c2 - 0xDC00)))
                    j += 4
                else:
                    j += 2
            else:
                j += 2
        elif 0xDC00 <= c <= 0xDFFF:
            j += 2
        else:
            chars.append(chr(c)); j += 2
    return "".join(chars)


def iter_records(raw: bytes):
    i = 0
    while i < len(raw) - 3:
        header = struct.unpack("<I", raw[i:i + 4])[0]
        tag = header & 0x3FF
        size = (header >> 20) & 0xFFF
        i += 4
        if size == 0xFFF:
            if i + 4 > len(raw):
                return
            size = struct.unpack("<I", raw[i:i + 4])[0]
            i += 4
        yield tag, raw[i:i + size]
        i += size


def _inflate(raw: bytes) -> bytes | None:
    for wbits in (-15, 15):
        try:
            return zlib.decompress(raw, wbits)
        except zlib.error:
            continue
    return None


def sniff_ext(data: bytes) -> str | None:
    if data[:2] == b"\xff\xd8": return "jpg"
    if data[:4] == b"\x89PNG": return "png"
    if data[:2] == b"BM": return "bmp"
    if data[:4] == b"GIF8": return "gif"
    if data[:4] in (b"II*\x00", b"MM\x00*"): return "tif"
    return None


def hwp_text(path) -> str:
    ole = olefile.OleFileIO(str(path))
    try:
        hdr = ole.openstream("FileHeader").read()
        compressed = bool(struct.unpack("<I", hdr[36:40])[0] & 1)
        sections = [e for e in ole.listdir() if e[0] == "BodyText"]
        sections.sort(key=lambda e: int("".join(ch for ch in e[-1] if ch.isdigit()) or 0))
        paras: list[str] = []
        for e in sections:
            raw = ole.openstream(e).read()
            if compressed:
                raw = _inflate(raw) or b""
            for tag, payload in iter_records(raw):
                if tag == HWPTAG_PARA_TEXT:
                    paras.append(decode_para_text(payload))
        text = "\n".join(paras)
        if not text.strip() and ole.exists("PrvText"):
            text = ole.openstream("PrvText").read().decode("utf-16-le", "ignore")
        return text
    finally:
        ole.close()


def hwp_images(path, out_dir: Path, stem: str) -> tuple[list[dict], list[str]]:
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    images, warnings = [], []
    ole = olefile.OleFileIO(str(path))
    try:
        n = 0
        for e in ole.listdir():
            if e[0] != "BinData":
                continue
            raw = ole.openstream(e).read()
            data = raw if sniff_ext(raw) else (_inflate(raw) or raw)
            ext = sniff_ext(data)
            if not ext:
                warnings.append(f"skip non-image stream {'/'.join(e)}")
                continue
            try:
                im = Image.open(io.BytesIO(data)); im.load()
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"unreadable image {'/'.join(e)}: {exc}")
                continue
            rec = save_image(im, out_dir, stem, n + 1, origin=f"{Path(path).name}:{'/'.join(e)}", prefer_jpg=(ext == "jpg"))
            if rec is None:
                warnings.append(f"skip tiny image {'/'.join(e)} {im.size}")
                continue
            n += 1
            images.append(rec)
    finally:
        ole.close()
    return images, warnings


def extract(path, out_dir) -> dict:
    path = Path(path)
    text = hwp_text(path)
    images, warnings = hwp_images(path, Path(out_dir), path.stem[:40])
    return {"text": text, "images": images, "warnings": warnings}
