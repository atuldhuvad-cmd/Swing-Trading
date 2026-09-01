"""Render selected PDF pages to PNG for visual/OCR inspection."""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

PDF_DIR = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings\pdfs")
OUT = Path(r"D:\Swing Trading\scratch\pdf_renders")
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    sym = sys.argv[1]
    pages = [int(x) for x in sys.argv[2].split(",")]
    zoom = float(sys.argv[3]) if len(sys.argv) > 3 else 1.6
    doc = pymupdf.open(PDF_DIR / f"{sym}_FY2025-26_annual.pdf")
    mat = pymupdf.Matrix(zoom, zoom)
    for pno in pages:
        pix = doc[pno - 1].get_pixmap(matrix=mat, alpha=False)
        dest = OUT / f"{sym}_p{pno}.png"
        pix.save(str(dest))
        print(dest, pix.width, pix.height)


if __name__ == "__main__":
    main()
