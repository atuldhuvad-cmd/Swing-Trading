"""Print word-level coordinates around a needle on a PDF page."""
from __future__ import annotations

import sys

import pymupdf

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PDF_DIR = r"D:\Swing Trading\manual_inputs\fundamentals\filings\pdfs"


def main() -> None:
    sym, page_no = sys.argv[1], int(sys.argv[2])
    needle = sys.argv[3].lower() if len(sys.argv) > 3 else None
    doc = pymupdf.open(f"{PDF_DIR}\\{sym}_FY2025-26_annual.pdf")
    page = doc[page_no - 1]
    words = page.get_text("words")  # x0,y0,x1,y1,word,block,line,word_no
    print(f"{sym} p{page_no} words={len(words)}")
    for w in words:
        x0, y0, x1, y1, text = w[:5]
        if needle and needle not in text.lower() and not any(ch.isdigit() for ch in text):
            # still print header-ish short tokens
            if y0 < 120:
                print(f"({x0:7.1f},{y0:7.1f}) {text}")
            continue
        print(f"({x0:7.1f},{y0:7.1f}-{x1:7.1f}) {text}")


if __name__ == "__main__":
    main()
