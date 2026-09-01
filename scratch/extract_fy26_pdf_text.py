"""Extract P&L snippets around canonical revenue line items from FY26 PDFs."""
from __future__ import annotations

import json
import re
from pathlib import Path

from pypdf import PdfReader

PDF_DIR = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings\pdfs")
OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")

LINE = {
    "ADANIENT": r"Revenue from operations",
    "ADANIPORTS": r"Revenue from operations",
    "APOLLOHOSP": r"Revenue from operations",
    "ASIANPAINT": r"Revenue from operations",
    "AXISBANK": r"Total Income",
    "BAJAJ-AUTO": r"Revenue from operations",
    "BAJAJFINSV": r"Revenue from operations",
    "BAJFINANCE": r"Total Income",
    "BEL": r"Revenue from operations",
    "BHARTIARTL": r"Revenue from operations",
}


def main() -> None:
    report = {}
    for pdf in sorted(PDF_DIR.glob("*.pdf")):
        sym = pdf.name.split("_")[0]
        if pdf.name.startswith("BAJAJ-AUTO"):
            sym = "BAJAJ-AUTO"
        reader = PdfReader(str(pdf))
        pages = []
        for i, page in enumerate(reader.pages):
            try:
                t = page.extract_text() or ""
            except Exception as e:
                t = f"[extract error: {e}]"
            pages.append(t)
        full = "\n\n----- PAGE {} -----\n".format
        blob = ""
        for i, t in enumerate(pages, 1):
            blob += f"\n\n----- PAGE {i} -----\n{t}"
        (OUT / f"{sym}_pdf_text.txt").write_text(blob, encoding="utf-8", errors="replace")
        pat = re.compile(LINE.get(sym, r"Revenue from operations"), re.I)
        hits = []
        for i, t in enumerate(pages, 1):
            if pat.search(t) or re.search(r"Rs\.?\s*in\s*crore|INR\s*crore|in Crores", t, re.I):
                if pat.search(t):
                    hits.append({"page": i, "excerpt": t[:4000]})
        report[sym] = {
            "pages": len(pages),
            "line_hits": len(hits),
            "first_hits": hits[:6],
        }
        print(sym, "pages", len(pages), "line_hits", len(hits))
    (OUT / "_pdf_line_hits.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
