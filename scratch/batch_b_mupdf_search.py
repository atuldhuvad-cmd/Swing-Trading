"""Search a Batch B PDF for a case-insensitive substring across all pages using PyMuPDF."""
from __future__ import annotations

import sys

import pymupdf

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PDF_DIR = r"D:\Swing Trading\manual_inputs\fundamentals\filings\pdfs"


def main() -> None:
    sym, needle = sys.argv[1], sys.argv[2].lower()
    doc = pymupdf.open(f"{PDF_DIR}\\{sym}_FY2025-26_annual.pdf")
    for pno in range(len(doc)):
        for line in doc[pno].get_text().splitlines():
            if needle in line.lower():
                print(f"p{pno + 1}: {line.strip()}")


if __name__ == "__main__":
    main()
