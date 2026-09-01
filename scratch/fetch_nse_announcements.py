"""Download NSE corporate announcements and keep FY26 annual result PDF candidates."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

import requests

OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")
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
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}

KEYS = re.compile(
    r"financial.?result|audited|annual.?result|year ended|fy ?26|fy2026|march 31, 2026|31\.03\.2026|31-03-2026|integrated filing",
    re.I,
)


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://www.nseindia.com/", timeout=30)
    s.get("https://www.nseindia.com/companies-listing/corporate-filings-announcements", timeout=30)
    return s


def flatten(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("data", "announcements", "corporateAnnouncements"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
        return [obj]
    return []


def text_of(item: dict) -> str:
    parts = []
    for k, v in item.items():
        if isinstance(v, (str, int, float)):
            parts.append(str(v))
    return " | ".join(parts)


def main() -> None:
    s = session()
    index = []
    for sym in SYMBOLS:
        url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={quote(sym)}"
        r = s.get(url, timeout=60)
        path = OUT / f"{sym}_announcements.json"
        path.write_text(r.text, encoding="utf-8")
        items = flatten(r.json()) if r.status_code == 200 else []
        hits = []
        for item in items:
            if not isinstance(item, dict):
                continue
            blob = text_of(item)
            if KEYS.search(blob):
                hits.append(item)
        (OUT / f"{sym}_announcement_hits.json").write_text(
            json.dumps(hits[:50], indent=2, default=str), encoding="utf-8"
        )
        index.append({"symbol": sym, "http": r.status_code, "items": len(items), "hits": len(hits)})
        print(sym, r.status_code, "items", len(items), "hits", len(hits))
    (OUT / "_announcement_index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
