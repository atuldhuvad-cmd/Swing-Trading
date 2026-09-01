"""Fetch NSE integrated-filing-results for Batch A symbols."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import requests

OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")
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
    "Referer": "https://www.nseindia.com/companies-listing/corporate-integrated-filing?integratedType=integratedfilingfinancials",
}


def main() -> None:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://www.nseindia.com/", timeout=30)
    s.get(
        "https://www.nseindia.com/companies-listing/corporate-integrated-filing?integratedType=integratedfilingfinancials",
        timeout=30,
    )
    templates = [
        "https://www.nseindia.com/api/integrated-filing-results?index=equities&type=Integrated%20Filing-%20Financials&symbol={sym}&page=1&size=50",
        "https://www.nseindia.com/api/integrated-filing-results?type=Integrated%20Filing-%20Financials&symbol={sym}&page=1&size=50",
        "https://www.nseindia.com/api/integrated-filing-results?symbol={sym}&type=Integrated%20Filing-%20Financials",
    ]
    # first probe ADANIENT
    probe = []
    for tmpl in templates:
        url = tmpl.format(sym=quote("ADANIENT"))
        r = s.get(url, timeout=45)
        probe.append({"url": url, "status": r.status_code, "len": len(r.text), "head": r.text[:600]})
        print(r.status_code, len(r.text), url)
    (OUT / "_integrated_probe.json").write_text(json.dumps(probe, indent=2), encoding="utf-8")

    # also fetch generic first page
    r = s.get(
        "https://www.nseindia.com/api/integrated-filing-results?&type=Integrated%20Filing-%20Financials&page=1&size=50",
        timeout=45,
    )
    (OUT / "_integrated_page1.json").write_text(r.text[:300000], encoding="utf-8")
    print("page1", r.status_code, len(r.text))


if __name__ == "__main__":
    main()
