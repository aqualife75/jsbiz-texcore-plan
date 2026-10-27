# -*- coding: utf-8 -*-
"""주입 엔진 샘플 회귀 테스트: tests/fixtures/fill_sample.json → tests/_out/fill_out/(hwpx·hwp·pdf·page-NN.png·qa_report).

python -X utf8 scripts/run_fill_sample.py [--spec tests/fixtures/fill_sample.json] [--out tests/_out/fill_out] [--name sample_filled]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "texcore-plan" / "skills" / "texcore-plan" / "scripts"))
import hwp_fill  # noqa: E402
import render_qa  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default=str(ROOT / "tests" / "fixtures" / "fill_sample.json"))
    ap.add_argument("--out", default=str(ROOT / "tests" / "_out" / "fill_out"))
    ap.add_argument("--name", default="sample_filled")
    ap.add_argument("--master", default=str(ROOT / "plugins" / "texcore-plan" / "skills" / "texcore-plan" / "assets" / "template" / "template_master.hwpx"))
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rep = hwp_fill.fill(a.master, a.spec, out / f"{a.name}.hwpx", hwp=out / f"{a.name}.hwp",
                        pdf=out / f"{a.name}.pdf")
    (out / "fill_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    qa = render_qa.render(out / f"{a.name}.hwpx", out, dpi=110, pdf=out / f"{a.name}.pdf")
    print(json.dumps({"pages": rep["pages"], "leftover": rep["leftover_tokens"], "warnings": rep["warnings"],
                      "qa_blocking": qa["blocking"], "qa_warnings": qa["warnings"]}, ensure_ascii=False, indent=2))
    return 0 if qa["pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
