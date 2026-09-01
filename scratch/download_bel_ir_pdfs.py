"""Download BEL official FY26 result PDFs, skipping SSL verify due to local cert store."""
from __future__ import annotations

from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()

OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings\pdfs")
OUT.mkdir(parents=True, exist_ok=True)
URLS = {
    "BEL_company_board_outcome_19May2026.pdf": "https://bel-india.in/wp-content/uploads/2026/05/Outcome-of-Board-Meeting-19.05.2026-1-1.pdf",
    "BEL_newspaper_extracts_FY26.pdf": "https://bel-india.in/wp-content/uploads/2026/04/Newspaper-publication-of-Extracts-of-Standalone-Consolidated-Audited-Financial-Results-for-the-Quarter-and-Year-ended-31.03.2026-(2).pdf",
    "BEL_2025-26-Q4-Financial-Results.pdf": "https://bel-india.in/wp-content/uploads/2026/05/BEL-2025-26-Q4-Financial-Results.pdf",
    "BEL_Q4_FY26_Financial_Results.pdf": "https://bel-india.in/wp-content/uploads/2026/05/BEL-Q4-FY26-Financial-Results.pdf",
}

headers = {"User-Agent": "Mozilla/5.0"}
for name, url in URLS.items():
    try:
        r = requests.get(url, headers=headers, timeout=60, verify=False)
        dest = OUT / name
        dest.write_bytes(r.content)
        print(name, r.status_code, len(r.content), r.headers.get("Content-Type"), r.content[:5])
    except Exception as e:
        print("ERR", name, e)
