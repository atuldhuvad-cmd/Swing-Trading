"""Extract full text of Batch B FY2025-26 result PDFs for canonical line-item review."""
from __future__ import annotations

import json
from pathlib import Path

from pypdf import PdfReader

PDF_DIR = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings\pdfs")
OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")

SYMBOLS = ["CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
           "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO"]


def main() -> None:
    report = {}
    for sym in SYMBOLS:
        pdf = PDF_DIR / f"{sym}_FY2025-26_annual.pdf"
        reader = PdfReader(str(pdf))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception as e:
                pages.append(f"[extract error: {e}]")
        blob = "".join(f"\n\n----- PAGE {i} -----\n{t}" for i, t in enumerate(pages, 1))
        (OUT / f"{sym}_batchb_pdf_text.txt").write_text(blob, encoding="utf-8", errors="replace")
        report[sym] = {"pages": len(pages), "chars": len(blob)}
        print(sym, "pages", len(pages), "chars", len(blob))
    (OUT / "_batch_b_pdf_text_index.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
