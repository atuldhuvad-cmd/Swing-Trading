"""Probe NSE integrated-filing APIs for Batch A annual results."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import requests

OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")
OUT.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-integrated-filing-financials",
}

CANDIDATES = [
    "https://www.nseindia.com/api/integrated-filings-financials?index=equities&symbol={sym}",
    "https://www.nseindia.com/api/corporate-filings-integrated-financials?index=equities&symbol={sym}",
    "https://www.nseindia.com/api/integrated-filing-financials?index=equities&symbol={sym}&from_date=01-01-2025&to_date=14-08-2026",
    "https://www.nseindia.com/api/corporates-integrated-filings?index=equities&symbol={sym}",
    "https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={sym}&issuer={sym}",
    "https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={sym}",
]


def main() -> None:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://www.nseindia.com/", timeout=30)
    s.get(
        "https://www.nseindia.com/companies-listing/corporate-filings-integrated-filing-financials",
        timeout=30,
    )
    # Probe with one liquid symbol
    results = []
    for tmpl in CANDIDATES:
        url = tmpl.format(sym=quote("ADANIENT"))
        try:
            r = s.get(url, timeout=30)
            snippet = r.text[:400]
            results.append({"url": url, "status": r.status_code, "len": len(r.text), "snippet": snippet})
            print(r.status_code, len(r.text), url)
        except Exception as e:
            results.append({"url": url, "error": str(e)})
            print("ERR", url, e)
    (OUT / "_nse_api_probe.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
