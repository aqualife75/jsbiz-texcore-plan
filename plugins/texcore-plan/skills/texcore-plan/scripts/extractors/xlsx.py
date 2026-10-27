# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import openpyxl

MAX_ROWS = 500

def extract(path, out_dir) -> dict:
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    lines, warnings = [], []
    for ws in wb.worksheets:
        lines.append(f"[시트: {ws.title}]")
        for r, row in enumerate(ws.iter_rows(values_only=True), 1):
            if r > MAX_ROWS:
                warnings.append(f"{ws.title}: rows limited to {MAX_ROWS}"); break
            if any(v is not None for v in row):
                lines.append(" | ".join("" if v is None else str(v) for v in row))
    return {"text": "\n".join(lines), "images": [], "warnings": warnings}
