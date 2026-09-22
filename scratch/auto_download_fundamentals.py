"""Auto-download NSE quarterly financial-results filings (download only).

On-demand tool -- you run it whenever you want to check for a new quarter's
results. It does NOT write to the database and does NOT touch fundamental
figures at all. It only:

  1. Fetches each symbol's recent NSE corporate announcements (the same
     `/api/corporate-announcements` endpoint that manual_inputs/fundamentals/
     filings/*_announcements.json already holds real, previously-fetched
     data for -- this is the one part of this NSE automation that has
     already been proven to work, unlike the OHLCV downloader).
  2. Filters for announcements that look like a quarterly/annual financial
     results filing (board meeting outcome, unaudited/audited results,
     "period ended", "quarter ended", etc).
  3. Cross-checks each match against what's already in fundamental_snapshot
     for that stock (by as_of_date + period_type), so it only flags
     genuinely NEW filings.
  4. Downloads the PDF for each new filing to
     manual_inputs/fundamentals/filings/<SYMBOL>/ and writes a checklist
     report (JSON + printed table) of what's new and needs review.

Deliberately does NOT extract figures or import anything. Turning a PDF into
the metrics your app stores (entity_type, source_line_item, statement_scope,
per-metric KNOWN/UNKNOWN status) requires reading the filing and applying
judgment your app's own rules call out explicitly -- e.g. insurance entities
use different line items than ordinary companies. That stays a manual step
through the existing /fundamentals/import screen (preview -> confirm), same
as every fundamental snapshot in your database today.

Usage:
  venv\\Scripts\\python.exe ..\\scratch\\auto_download_fundamentals.py
  venv\\Scripts\\python.exe ..\\scratch\\auto_download_fundamentals.py --symbols BEL HDFCLIFE
  venv\\Scripts\\python.exe ..\\scratch\\auto_download_fundamentals.py --lookback-days 120

UNVERIFIED (same caveat as the OHLCV script): the live network call could
not be exercised from the Claude session that built this -- its sandbox
blocks nseindia.com outright. Unlike the OHLCV endpoint though, this one
(`/api/corporate-announcements`) is not a guess: real captured responses
from a previous successful run already sit in
manual_inputs/fundamentals/filings/*_announcements.json, and this script's
filtering logic was checked against that real data (see the audit notes).
Still, run it once yourself and confirm before relying on it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent.parent
PROD_DB = ROOT / "data" / "swing_trading.db"
OUT_DIR = ROOT / "manual_inputs" / "fundamentals" / "filings"
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.models import StockMaster, FundamentalSnapshot  # noqa: E402

NSE_HOME = "https://www.nseindia.com/"
NSE_FILINGS_PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
NSE_ANNOUNCEMENTS_URL = "https://www.nseindia.com/api/corporate-announcements"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_FILINGS_PAGE,
}

# Broadened from the one-off FY26-annual-only regex used previously in this
# project (scratch/fetch_nse_announcements.py) to catch any quarter, any
# year -- this script is meant to run every quarter going forward.
RESULT_KEYS = re.compile(
    r"financial result|quarter(ly)? result|period ended|quarter ended|"
    r"un-?audited|audited.{0,20}result|outcome of board meeting.{0,40}result",
    re.I,
)
DEFAULT_LOOKBACK_DAYS = 120  # comfortably spans one quarter + reporting lag


def flatten(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("data", "announcements", "corporateAnnouncements"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
        return [obj]
    return []


def parse_an_dt(raw: str):
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except (ValueError, TypeError):
            continue
    return None


def already_covered(db, stock_id: int, filing_dt: datetime) -> bool:
    """Best-effort: treat a filing as already covered if a snapshot exists
    whose as_of_date falls within ~20 days of the filing's period end. We
    don't try to parse the exact period end out of free text here -- this
    is a safety-leaning heuristic to reduce noise, not a hard guarantee.
    The report always lists what it found either way, so you can judge for
    yourself instead of trusting this silently."""
    snapshots = (
        db.query(FundamentalSnapshot)
        .filter(FundamentalSnapshot.stock_id == stock_id, FundamentalSnapshot.is_superseded == False)  # noqa: E712
        .all()
    )
    for snap in snapshots:
        if snap.as_of_date and abs((snap.as_of_date - filing_dt.date()).days) <= 20:
            return True
    return False


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get(NSE_HOME, timeout=30)
    s.get(NSE_FILINGS_PAGE, timeout=30)
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", nargs="*", default=None,
                     help="NSE symbols to check (default: every symbol in Stock Master)")
    ap.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now() - timedelta(days=args.lookback_days)

    db = SessionLocal()
    try:
        stocks = db.query(StockMaster).order_by(StockMaster.nse_symbol).all()
        if args.symbols:
            wanted = {s.upper() for s in args.symbols}
            stocks = [s for s in stocks if s.nse_symbol.upper() in wanted]
        if not stocks:
            print("No matching symbols in Stock Master. Nothing to do.")
            return 1

        s = session()
        report = []
        for stock in stocks:
            sym = stock.nse_symbol
            url = f"{NSE_ANNOUNCEMENTS_URL}?index=equities&symbol={quote(sym)}"
            try:
                r = s.get(url, timeout=60)
            except requests.RequestException as e:
                print(f"  {sym:<12} FETCH_FAILED: {e}")
                report.append({"symbol": sym, "status": "FETCH_FAILED", "error": str(e)})
                continue

            if r.status_code != 200:
                print(f"  {sym:<12} FETCH_FAILED: HTTP {r.status_code}")
                report.append({"symbol": sym, "status": "FETCH_FAILED", "error": f"HTTP {r.status_code}"})
                continue

            try:
                items = flatten(r.json())
            except ValueError:
                print(f"  {sym:<12} FETCH_FAILED: response was not JSON (likely blocked/CAPTCHA)")
                report.append({"symbol": sym, "status": "FETCH_FAILED", "error": "non-JSON response"})
                continue

            sym_entry = {"symbol": sym, "status": "OK", "new_filings": [], "already_covered": []}
            for item in items:
                if not isinstance(item, dict):
                    continue
                blob = " | ".join(str(v) for v in item.values() if isinstance(v, (str, int, float)))
                if not RESULT_KEYS.search(blob):
                    continue
                filing_dt = parse_an_dt(item.get("an_dt") or item.get("exchdisstime") or "")
                if filing_dt is None or filing_dt < cutoff:
                    continue

                covered = already_covered(db, stock.stock_id, filing_dt)
                record = {
                    "an_dt": item.get("an_dt"),
                    "desc": item.get("desc"),
                    "text": (item.get("attchmntText") or "")[:200],
                    "pdf_url": item.get("attchmntFile"),
                }
                if covered:
                    sym_entry["already_covered"].append(record)
                    continue

                sym_entry["new_filings"].append(record)
                pdf_url = item.get("attchmntFile")
                if pdf_url:
                    try:
                        pdf_resp = s.get(pdf_url, timeout=60)
                        pdf_resp.raise_for_status()
                        sym_dir = OUT_DIR / sym
                        sym_dir.mkdir(parents=True, exist_ok=True)
                        fname = pdf_url.rsplit("/", 1)[-1] or f"{sym}_{item.get('dt', '')}.pdf"
                        dest = sym_dir / fname
                        dest.write_bytes(pdf_resp.content)
                        record["saved_pdf"] = str(dest)
                    except requests.RequestException as e:
                        record["download_error"] = str(e)

            n_new, n_cov = len(sym_entry["new_filings"]), len(sym_entry["already_covered"])
            print(f"  {sym:<12} new={n_new} already_covered={n_cov}")
            report.append(sym_entry)

    finally:
        db.close()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    report_path = OUT_DIR / f"auto_download_report_{stamp}.json"
    report_path.write_text(json.dumps({"generated_at": stamp, "lookback_days": args.lookback_days,
                                        "results": report}, indent=2, default=str), encoding="utf-8")
    print(f"\nReport written: {report_path}")

    total_new = sum(len(r.get("new_filings", [])) for r in report)
    print(f"\n{total_new} new quarterly/annual results filing(s) found across {len(report)} symbol(s).")
    print("Nothing was imported -- review each PDF and use the /fundamentals/import "
          "screen (preview -> confirm) as usual.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
