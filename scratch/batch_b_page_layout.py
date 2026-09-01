"""Re-extract a single PDF page in layout mode (catches header/unit labels missed in plain mode)."""
from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PDF_DIR = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings\pdfs")


def main() -> None:
    sym, page_no = sys.argv[1], int(sys.argv[2])
    reader = PdfReader(str(PDF_DIR / f"{sym}_FY2025-26_annual.pdf"))
    page = reader.pages[page_no - 1]
    print(page.extract_text(extraction_mode="layout"))


if __name__ == "__main__":
    main()
