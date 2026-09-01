"""Dump pymupdf text + OCR status helpers for remaining Batch B pages."""
from __future__ import annotations

import sys

import pymupdf

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PDF_DIR = r"D:\Swing Trading\manual_inputs\fundamentals\filings\pdfs"


def dump(sym: str, page_no: int) -> None:
    doc = pymupdf.open(f"{PDF_DIR}\\{sym}_FY2025-26_annual.pdf")
    page = doc[page_no - 1]
    print(f"==== {sym} p{page_no} size={page.rect} images={len(page.get_images())} ====")
    print(page.get_text("text"))


def hdfcbank_overview() -> None:
    doc = pymupdf.open(f"{PDF_DIR}\\HDFCBANK_FY2025-26_annual.pdf")
    print("HDFCBANK pages", len(doc))
    for i, page in enumerate(doc, 1):
        t = page.get_text("text").strip()
        print(f"p{i}: chars={len(t)} images={len(page.get_images())} size={page.rect}")
        if t:
            print(t[:500])
            print("---")


if __name__ == "__main__":
    if sys.argv[1] == "hdfc":
        hdfcbank_overview()
    else:
        dump(sys.argv[1], int(sys.argv[2]))
