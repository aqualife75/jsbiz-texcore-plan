# -*- coding: utf-8 -*-
"""URL → 스크린샷 PNG(또는 PDF). Chrome/Edge 헤드리스 CLI만 사용(Playwright 불필요).
사용: python capture_evidence.py <url> <out.png> [--size 1440x2400] [--crop l,t,r,b] [--wait 6000] [--pdf out.pdf]
"""
from __future__ import annotations
import argparse, os, platform, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import prep_image  # noqa: E402

def find_chrome() -> str | None:
    sysname = platform.system(); cands = []
    if sysname == "Windows":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files"); pfx = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"); loc = os.environ.get("LOCALAPPDATA", "")
        cands += [rf"{pf}\Google\Chrome\Application\chrome.exe", rf"{pfx}\Google\Chrome\Application\chrome.exe", rf"{loc}\Google\Chrome\Application\chrome.exe",
                  rf"{pfx}\Microsoft\Edge\Application\msedge.exe", rf"{pf}\Microsoft\Edge\Application\msedge.exe"]
    elif sysname == "Darwin":
        cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "chrome", "msedge"):
        w = shutil.which(n)
        if w: cands.append(w)
    return next((c for c in cands if c and os.path.exists(c)), None)

def _run(args: list[str], timeout=90) -> str:
    """Chrome 헤드리스 1회 실행. 프로필 폴더는 **호출마다 새로** 만든다.

    같은 --user-data-dir를 여러 프로세스가 동시에 쓰면 Chrome이 프로필 잠금으로
    조용히 종료해 스크린샷이 생기지 않는다(조사 에이전트 병렬 실행 시 재현).
    """
    prof = tempfile.mkdtemp(prefix="seed_ir_chrome_")
    base = [find_chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
            "--run-all-compositor-stages-before-draw", f"--user-data-dir={prof}", "--lang=ko-KR"]
    try:
        r = subprocess.run(base + args, capture_output=True, text=True, timeout=timeout)
        return ((r.stderr or "") + (r.stdout or ""))[-400:]
    finally:
        shutil.rmtree(prof, ignore_errors=True)

def capture(url: str, out_png, width=1440, height=2400, wait_ms=6000) -> Path:
    if not find_chrome(): raise RuntimeError("Chrome/Edge를 찾지 못했습니다 — 설치 후 다시 시도")
    out_png = Path(out_png); out_png.parent.mkdir(parents=True, exist_ok=True)
    log = _run([f"--window-size={width},{height}", f"--virtual-time-budget={wait_ms}", f"--screenshot={out_png}", url])
    if not out_png.exists(): raise RuntimeError(f"캡처 실패: {url}\n{log}")
    return out_png

def capture_pdf(url: str, out_pdf) -> Path:
    out_pdf = Path(out_pdf); out_pdf.parent.mkdir(parents=True, exist_ok=True)
    log = _run(["--no-pdf-header-footer", f"--print-to-pdf={out_pdf}", url], timeout=120)
    if not out_pdf.exists(): raise RuntimeError(f"PDF 캡처 실패: {url}\n{log}")
    return out_pdf

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("url"); ap.add_argument("out"); ap.add_argument("--size", default="1440x2400")
    ap.add_argument("--crop", help="l,t,r,b px (캡처 후 잘라내기)"); ap.add_argument("--wait", type=int, default=6000); ap.add_argument("--pdf")
    a = ap.parse_args(argv); w, h = (int(v) for v in a.size.lower().split("x"))
    capture(a.url, a.out, w, h, a.wait)
    if a.crop: prep_image.crop(a.out, a.out, [int(v) for v in a.crop.split(",")])
    if a.pdf: capture_pdf(a.url, a.pdf)
    print(a.out); return 0

if __name__ == "__main__":
    sys.exit(main())
