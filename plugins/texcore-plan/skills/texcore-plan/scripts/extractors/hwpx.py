# -*- coding: utf-8 -*-
from __future__ import annotations
import html, io, re, zipfile
from pathlib import Path
from PIL import Image
from .images import save_image

# 자기닫힘 <hp:t/>를 여는 태그로 오인하면 다음 </hp:t>까지의 XML(표·그림 속성)이 본문으로 새어 나온다 → 제외.
_T = re.compile(r"<hp:t(?:\s[^>]*[^/>])?>(.*?)</hp:t>", re.S)
_TAG = re.compile(r"<[^>]+>")
_P_END = re.compile(r"</hp:p>")

def extract(path, out_dir) -> dict:
    path = Path(path); out_dir = Path(out_dir)
    text_parts, images, warnings = [], [], []
    with zipfile.ZipFile(path) as z:
        secs = sorted([n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n)],
                      key=lambda n: int(re.search(r"(\d+)", n.split("/")[-1]).group(1)))
        for n in secs:
            xml = z.read(n).decode("utf-8", "ignore")
            paras = []
            for chunk in _P_END.split(xml):
                t = "".join(html.unescape(_TAG.sub(" ", m)) for m in _T.findall(chunk))
                if t.strip():
                    paras.append(t)
            text_parts.append("\n".join(paras))
        k = 0
        for n in z.namelist():
            if n.startswith("BinData/") and not n.endswith("/"):
                try:
                    im = Image.open(io.BytesIO(z.read(n))); im.load()
                except Exception:  # noqa: BLE001
                    warnings.append(f"skip non-image {n}"); continue
                k += 1
                rec = save_image(im, out_dir, path.stem[:40], k, f"{path.name}:{n}")
                if rec: images.append(rec)
    return {"text": "\n".join(text_parts), "images": images, "warnings": warnings}
