"""Locate NSE corporate filings for Batch A annual FY2025-26 results. Does not write production DB."""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

ROOT = Path(r"D:\Swing Trading")
OUT = ROOT / "manual_inputs" / "fundamentals" / "filings"
OUT.mkdir(parents=True, exist_ok=True)

SYMBOLS = [
    "ADANIENT",
    "ADANIPORTS",
    "APOLLOHOSP",
    "ASIANPAINT",
    "AXISBANK",
    "BAJAJ-AUTO",
    "BAJAJFINSV",
    "BAJFINANCE",
    "BEL",
    "BHARTIARTL",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results",
}


def nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://www.nseindia.com/", timeout=30)
    s.get("https://www.nseindia.com/companies-listing/corporate-filings-financial-results", timeout=30)
    return s


def main() -> None:
    s = nse_session()
    summary = []
    for sym in SYMBOLS:
        url = (
            "https://www.nseindia.com/api/corporates-financial-results"
            f"?index=equities&symbol={requests.utils.quote(sym)}"
            "&period=Annual&from_date=01-01-2025&to_date=14-08-2026"
        )
        row = {"symbol": sym, "url": url, "status": None, "error": None, "count": 0, "items": []}
        try:
            r = s.get(url, timeout=45)
            row["status"] = r.status_code
            if r.status_code != 200:
                row["error"] = r.text[:500]
            else:
                data = r.json()
                if isinstance(data, dict):
                    items = data.get("data") or data.get("financialResults") or data
                    if isinstance(items, dict):
                        items = [items]
                elif isinstance(data, list):
                    items = data
                else:
                    items = []
                row["count"] = len(items) if isinstance(items, list) else 0
                row["items"] = items[:20] if isinstance(items, list) else items
                (OUT / f"{sym}_nse_financial_results.json").write_text(
                    json.dumps(data, indent=2)[:200000], encoding="utf-8"
                )
        except Exception as e:
            row["error"] = str(e)
        summary.append(row)
        print(sym, row["status"], row["count"], (row["error"] or "")[:120])

    (OUT / "_nse_index.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
