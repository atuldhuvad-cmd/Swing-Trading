"""Dump text spans (including rotated text) of a PDF page using PyMuPDF."""
from __future__ import annotations

import sys

import pymupdf

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PDF_DIR = r"D:\Swing Trading\manual_inputs\fundamentals\filings\pdfs"


def main() -> None:
    sym, page_no = sys.argv[1], int(sys.argv[2])
    grep = sys.argv[3].lower() if len(sys.argv) > 3 else None
    doc = pymupdf.open(f"{PDF_DIR}\\{sym}_FY2025-26_annual.pdf")
    page = doc[page_no - 1]
    data = page.get_text("dict")
    for block in data["blocks"]:
        for line in block.get("lines", []):
            txt = "".join(s["text"] for s in line["spans"]).strip()
            if not txt:
                continue
            if grep and grep not in txt.lower():
                continue
            x, y = line["bbox"][0], line["bbox"][1]
            print(f"({x:7.1f},{y:7.1f}) dir={line.get('dir')} | {txt}")


if __name__ == "__main__":
    main()
