"""Download NSE corporate announcements for Batch B and keep FY26 annual result candidates."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

import requests

OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")
OUT.mkdir(parents=True, exist_ok=True)

SYMBOLS = ["CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
           "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}

KEYS = re.compile(
    r"financial.?result|audited|annual.?result|year ended|fy ?26|fy2026|"
    r"march 31, 2026|31\.03\.2026|31-03-2026|integrated filing",
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
    return " | ".join(str(v) for v in item.values() if isinstance(v, (str, int, float)))


def main() -> None:
    s = session()
    index = []
    for sym in SYMBOLS:
        row = {"symbol": sym, "http": None, "items": 0, "hits": 0, "error": None}
        try:
            url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={quote(sym)}"
            r = s.get(url, timeout=60)
            row["http"] = r.status_code
            (OUT / f"{sym}_announcements.json").write_text(r.text, encoding="utf-8")
            items = flatten(r.json()) if r.status_code == 200 else []
            hits = [i for i in items if isinstance(i, dict) and KEYS.search(text_of(i))]
            (OUT / f"{sym}_announcement_hits.json").write_text(
                json.dumps(hits[:60], indent=2, default=str), encoding="utf-8")
            row["items"], row["hits"] = len(items), len(hits)
        except Exception as e:
            row["error"] = str(e)[:300]
        index.append(row)
        print(sym, row["http"], "items", row["items"], "hits", row["hits"], row["error"] or "")
    (OUT / "_batch_b_announcement_index.json").write_text(
        json.dumps(index, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
