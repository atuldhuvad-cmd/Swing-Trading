"""Forensic extraction of canonical revenue lines from Batch B FY26 PDFs."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pymupdf

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PDF_DIR = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings\pdfs")
OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")
SYMBOLS = [
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
]
NEEDLES = re.compile(
    r"revenue from operat|total revenue from operat|total income|total \(2 to 5\)|"
    r"policyholders|shareholders' a|interest earned|"
    r"in crore|in lakh|in million|rs\. in|indian rupees",
    re.I,
)


def page_lines(page) -> list[str]:
    return [ln.strip() for ln in page.get_text("text").splitlines() if ln.strip()]


def main() -> None:
    report = {}
    for sym in SYMBOLS:
        path = PDF_DIR / f"{sym}_FY2025-26_annual.pdf"
        doc = pymupdf.open(path)
        hits = []
        empty = 0
        for i, page in enumerate(doc, 1):
            lines = page_lines(page)
            if len("".join(lines)) < 40:
                empty += 1
            for j, line in enumerate(lines):
                if NEEDLES.search(line):
                    ctx = lines[max(0, j - 3): min(len(lines), j + 6)]
                    hits.append({"page": i, "line": line, "ctx": ctx})
        report[sym] = {
            "pages": len(doc),
            "emptyish_pages": empty,
            "hits": hits[:80],
            "hit_count": len(hits),
        }
        print(f"{sym}: pages={len(doc)} emptyish={empty} hits={len(hits)}")
        for h in hits[:12]:
            print(f"  p{h['page']}: {h['line'][:140]}")
        print()
    (OUT / "_batch_b_canonical_hits.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
