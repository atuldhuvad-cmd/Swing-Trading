"""Auto-download NSE OHLCV data (per-symbol historical CSVs AND the daily
full-market Bhavcopy) and import it. Both run by default -- they're
complementary, not alternatives: per-symbol backfills a date range per
stock, Bhavcopy is one file per trading day covering the whole market (your
app only picks out rows for symbols already in your Stock Master, so
importing it is safe even though it lists thousands of unrelated symbols).

On-demand tool: run it yourself whenever you want fresh data. Nothing here
runs on a schedule or without you invoking it.

PER-SYMBOL, for each symbol in your Stock Master (or --symbols):
  1. Works out a date range: from the day after your latest stored session
     for that symbol (incremental), or --lookback-days back from today if
     you have no history yet for it.
  2. Downloads that symbol's historical OHLCV CSV from NSE's website, in the
     exact format NSE's own "Download (.csv)" button produces (same layout
     as your existing manual_inputs/nse and manual_inputs/nifty50 files).

BHAVCOPY, for each calendar day from --bhavcopy-from to --bhavcopy-to
(default: the last 7 days through today):
  1. Downloads that day's official full-market end-of-day file from NSE's
     archive (same file, same URL pattern, as the
     manual_inputs/nse/BhavCopy_NSE_CM_0_0_0_20260812_F_0000.csv.zip you
     already downloaded by hand -- see the verification note below).
  2. A missing day (weekend/holiday, or not yet published) is skipped, not
     treated as a failure.

BOTH paths then:
  3. Save the raw download under manual_inputs/nse/auto/ (kept as evidence,
     mirrors your existing convention of keeping source files).
  4. Validate the file looks like real NSE data before doing anything else
     with it (aborts that item otherwise -- never imports an error page or
     CAPTCHA response as if it were data).
  5. Import via the SAME app.services.ohlcv_service.OhlcvService.confirm_import
     your Import screen uses -- no separate/duplicate import logic here, so
     the existing dedup/validation rules apply unchanged (re-running this is
     safe -- rows already in the DB are reported as duplicates, not
     re-inserted).
Before either path writes anything, data/swing_trading.db is backed up
first (matches your maintenance plan's "always backup before a bulk OHLCV
production import" rule), unless --no-backup is passed. A single JSON run
report is written under manual_inputs/nse/auto/.

Usage (from the backend venv):
  venv\\Scripts\\python.exe ..\\scratch\\auto_download_ohlcv.py
  venv\\Scripts\\python.exe ..\\scratch\\auto_download_ohlcv.py --symbols RELIANCE HDFCBANK
  venv\\Scripts\\python.exe ..\\scratch\\auto_download_ohlcv.py --dry-run        (download+save only, no import)
  venv\\Scripts\\python.exe ..\\scratch\\auto_download_ohlcv.py --no-backup      (skip the DB backup step)
  venv\\Scripts\\python.exe ..\\scratch\\auto_download_ohlcv.py --skip-bhavcopy  (per-symbol only)
  venv\\Scripts\\python.exe ..\\scratch\\auto_download_ohlcv.py --skip-symbols   (bhavcopy only)
  venv\\Scripts\\python.exe ..\\scratch\\auto_download_ohlcv.py --bhavcopy-from 01-08-2026 --bhavcopy-to 02-09-2026

VERIFICATION STATUS (different for each path):
- Bhavcopy: the exact URL this script uses was fetched successfully (real
  binary zip content came back, not an error page) during the same Claude
  session that built this script -- but from Claude's cloud research tool,
  not from this environment or your machine, so it's strong evidence, not
  a full proof it'll work for you. No login/cookie dance needed; it's a
  plain static archive file.
- Per-symbol: UNVERIFIED. Written from NSE's known historical-data export
  pattern but could not be fetched successfully from anywhere available
  during that session (nseindia.com's main site blocks the sandbox that
  built this outright). NSE occasionally changes this endpoint or serves a
  CAPTCHA/JS challenge instead of data -- this script will report the
  failure per-symbol rather than import garbage, but the fetch may simply
  need a different URL/params than what's here.
Run both once and tell Claude what happened (success, or the exact error)
so anything that needs adjusting gets fixed.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sqlite3
import sys
import time
import zipfile
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PROD_DB = ROOT / "data" / "swing_trading.db"
OUT_DIR = ROOT / "manual_inputs" / "nse" / "auto"
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.config import settings  # noqa: E402
from app.models import StockMaster, DailyOhlcv  # noqa: E402
from app.schemas.ohlcv import OhlcvConfirmRequest  # noqa: E402
from app.services.ohlcv_service import OhlcvService  # noqa: E402

NSE_HOME = "https://www.nseindia.com/"
NSE_REPORT_PAGE = "https://www.nseindia.com/report-detail/eq_security"
# Known NSE endpoint for the same CSV the "Historical Data" page's download
# button produces. UNVERIFIED live (see module docstring).
NSE_CSV_URL = "https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData"
# Official daily full-market end-of-day archive. Same pattern as your own
# manual_inputs/nse/BhavCopy_NSE_CM_0_0_0_20260812_F_0000.csv.zip filename.
# Verified reachable (see module docstring) -- no session cookies needed.
NSE_BHAVCOPY_URL_TMPL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{yyyymmdd}_F_0000.csv.zip"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/csv,application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_REPORT_PAGE,
}

DEFAULT_LOOKBACK_DAYS = 400  # enough for SMA200 + buffer when a symbol has no history yet
DEFAULT_BHAVCOPY_LOOKBACK_DAYS = 7  # bhavcopy is meant for routine day-to-day catch-up


def _looks_like_nse_csv(content: bytes) -> bool:
    """Reject HTML error pages / CAPTCHA / JSON error bodies before we go near the DB."""
    if not content or len(content) < 100:
        return False
    head = content[:2000].decode("utf-8-sig", errors="ignore").lstrip()
    if head.startswith("<") or head.startswith("{"):
        return False
    return '"Symbol' in head or "Symbol" in head.split("\n", 1)[0]


def fetch_symbol_csv(session: requests.Session, symbol: str, date_from: str, date_to: str) -> bytes:
    params = {
        "symbol": symbol,
        "series": "EQ",
        "from": date_from,   # DD-MM-YYYY
        "to": date_to,       # DD-MM-YYYY
        "type": "priceVolumeDeliverable",
        "csv": "true",
    }
    resp = session.get(NSE_CSV_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content


def fetch_bhavcopy(session: requests.Session, day: datetime) -> tuple[bytes, bytes] | None:
    """Returns (zip_bytes, extracted_csv_bytes), or None if that day has no
    bhavcopy (weekend/holiday/not yet published -- a 404 here is normal,
    not an error)."""
    url = NSE_BHAVCOPY_URL_TMPL.format(yyyymmdd=day.strftime("%Y%m%d"))
    resp = session.get(url, headers=HEADERS, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    zip_bytes = resp.content
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not names:
                raise ValueError(f"No CSV found inside bhavcopy zip for {day.date()}")
            csv_bytes = zf.read(names[0])
    except zipfile.BadZipFile as e:
        raise ValueError(f"Bhavcopy for {day.date()} did not look like a real zip file: {e}")
    return zip_bytes, csv_bytes


def configured_db_path() -> Path:
    prefix = "sqlite:///"
    if not settings.database_url.startswith(prefix) or ":memory:" in settings.database_url:
        raise RuntimeError("Automated OHLCV refresh requires a file-backed SQLite database")
    return Path(settings.database_url[len(prefix):]).resolve()


def backup_database(source_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = source_path.parent / f"{source_path.stem}_backup_{stamp}.db"
    with closing(sqlite3.connect(f"{source_path.as_uri()}?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(dest)) as backup:
            source.backup(backup)
            if backup.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise RuntimeError("Pre-import backup failed integrity check")
    return dest


def latest_trading_date(db, stock_id: int):
    row = (
        db.query(DailyOhlcv.trading_date)
        .filter(DailyOhlcv.stock_id == stock_id)
        .order_by(DailyOhlcv.trading_date.desc())
        .first()
    )
    return row[0] if row and row[0] else None


def import_ohlcv_bytes(content: bytes, filename: str, source_name: str, source_reference: str) -> dict:
    db = SessionLocal()
    try:
        sha = hashlib.sha256(content).hexdigest()
        req = OhlcvConfirmRequest(
            file_sha256=sha,
            original_filename=filename,
            source_name=source_name,
            source_reference=source_reference,
        )
        return OhlcvService.confirm_import(db, req, content)
    finally:
        db.close()


def run_symbols(args, today: datetime, date_to: str) -> list[dict]:
    # If Bhavcopy already ran earlier in this same invocation (the default),
    # it may have just inserted today's row for every symbol -- in that case
    # date_from (the day after the latest stored row) lands AFTER date_to,
    # an empty/inverted range. Fetching that from NSE anyway used to come
    # back as a CSV-shaped but rowless response, which failed import and
    # was misreported as IMPORT_FAILED for every symbol even though nothing
    # was actually wrong. Skip those cleanly instead.
    date_to_dt = datetime.strptime(date_to, "%d-%m-%Y")

    db = SessionLocal()
    try:
        stocks = db.query(StockMaster).order_by(StockMaster.nse_symbol).all()
        if args.symbols:
            wanted = {s.upper() for s in args.symbols}
            stocks = [s for s in stocks if s.nse_symbol.upper() in wanted]
        if not stocks:
            print("No matching symbols in Stock Master. Nothing to do for per-symbol fetch.")
            return []

        plan = []
        up_to_date: list[dict] = []
        for s in stocks:
            latest = latest_trading_date(db, s.stock_id)
            if latest:
                date_from_dt = latest + timedelta(days=1)
            else:
                date_from_dt = today - timedelta(days=args.lookback_days)
            # latest_trading_date() returns a plain date (SQLAlchemy Date
            # column), while today/date_to are datetimes -- normalize both
            # sides to date before comparing.
            date_from_date = date_from_dt.date() if isinstance(date_from_dt, datetime) else date_from_dt
            if date_from_date > date_to_dt.date():
                up_to_date.append({
                    "kind": "symbol", "symbol": s.nse_symbol, "status": "UP_TO_DATE",
                    "note": f"Already have data through {date_to} (e.g. from Bhavcopy) -- nothing to fetch.",
                })
                continue
            plan.append((s, date_from_dt.strftime("%d-%m-%Y")))
    finally:
        db.close()

    print(f"\n=== PER-SYMBOL: {len(plan)} symbol(s) to fetch, {len(up_to_date)} already up to date, through {date_to} ===")
    for s, date_from in plan:
        print(f"  {s.nse_symbol:<12} from {date_from}")
    for entry in up_to_date:
        print(f"  {entry['symbol']:<12} UP_TO_DATE")

    if not plan:
        return up_to_date

    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get(NSE_HOME, timeout=30)
        session.get(NSE_REPORT_PAGE, timeout=30)
    except requests.RequestException as e:
        print(f"WARNING: could not reach NSE to establish a session ({e}). Continuing anyway.")

    results = list(up_to_date)
    for s, date_from in plan:
        entry = {"kind": "symbol", "symbol": s.nse_symbol, "from": date_from, "to": date_to}
        try:
            content = fetch_symbol_csv(session, s.nse_symbol, date_from, date_to)
        except requests.RequestException as e:
            entry["status"] = "FETCH_FAILED"
            entry["error"] = str(e)
            print(f"  {s.nse_symbol:<12} FETCH_FAILED: {e}")
            results.append(entry)
            time.sleep(1.5)
            continue

        if not _looks_like_nse_csv(content):
            entry["status"] = "REJECTED_NOT_CSV"
            entry["error"] = "Response did not look like an NSE OHLCV CSV (HTML/JSON/empty) -- not imported"
            print(f"  {s.nse_symbol:<12} REJECTED_NOT_CSV (saved raw response for inspection)")
            raw_path = OUT_DIR / f"{date_from}-TO-{date_to}-{s.nse_symbol}-REJECTED.txt"
            raw_path.write_bytes(content)
            entry["saved_raw"] = str(raw_path)
            results.append(entry)
            time.sleep(1.5)
            continue

        filename = f"{date_from}-TO-{date_to}-{s.nse_symbol}-ALL-N.csv"
        csv_path = OUT_DIR / filename
        csv_path.write_bytes(content)
        entry["saved_csv"] = str(csv_path)

        if args.dry_run:
            entry["status"] = "DOWNLOADED_ONLY"
            print(f"  {s.nse_symbol:<12} downloaded -> {csv_path.name}")
            results.append(entry)
            time.sleep(1.5)
            continue

        try:
            res = import_ohlcv_bytes(content, filename, "NSE", f"manual_inputs/nse/auto/{filename}")
            entry["status"] = "IMPORTED"
            entry["result"] = res
            print(f"  {s.nse_symbol:<12} imported: inserted={res.get('inserted')} "
                  f"dup={res.get('rows_duplicates')} conflicts={res.get('rows_conflicts')} "
                  f"accepted={res.get('rows_accepted')} invalid={res.get('rows_invalid')} "
                  f"unmapped={res.get('rows_unmapped')} ignored={res.get('rows_ignored')}")
        except Exception as e:
            entry["status"] = "IMPORT_FAILED"
            entry["error"] = str(e)
            print(f"  {s.nse_symbol:<12} IMPORT_FAILED: {e}")

        results.append(entry)
        time.sleep(1.5)

    return results


def run_bhavcopy(args, today: datetime) -> list[dict]:
    date_from = datetime.strptime(args.bhavcopy_from, "%d-%m-%Y") if args.bhavcopy_from else \
        today - timedelta(days=DEFAULT_BHAVCOPY_LOOKBACK_DAYS)
    date_to = datetime.strptime(args.bhavcopy_to, "%d-%m-%Y") if args.bhavcopy_to else today

    days = []
    d = date_from
    while d.date() <= date_to.date():
        days.append(d)
        d += timedelta(days=1)

    print(f"\n=== BHAVCOPY: {len(days)} calendar day(s), {date_from.date()} to {date_to.date()} ===")

    session = requests.Session()
    session.headers.update(HEADERS)

    results = []
    for day in days:
        entry = {"kind": "bhavcopy", "date": day.strftime("%Y-%m-%d")}
        try:
            fetched = fetch_bhavcopy(session, day)
        except (requests.RequestException, ValueError) as e:
            entry["status"] = "FETCH_FAILED"
            entry["error"] = str(e)
            print(f"  {day.date()}  FETCH_FAILED: {e}")
            results.append(entry)
            time.sleep(1.0)
            continue

        if fetched is None:
            entry["status"] = "NO_FILE"  # weekend / holiday / not yet published -- not a failure
            print(f"  {day.date()}  no bhavcopy (holiday/weekend/not yet published)")
            results.append(entry)
            time.sleep(1.0)
            continue

        zip_bytes, csv_bytes = fetched
        stamp = day.strftime("%Y%m%d")
        zip_name = f"BhavCopy_NSE_CM_0_0_0_{stamp}_F_0000.csv.zip"
        csv_name = f"BhavCopy_NSE_CM_0_0_0_{stamp}_F_0000.csv"
        (OUT_DIR / zip_name).write_bytes(zip_bytes)
        (OUT_DIR / csv_name).write_bytes(csv_bytes)
        entry["saved_zip"] = str(OUT_DIR / zip_name)
        entry["saved_csv"] = str(OUT_DIR / csv_name)

        if args.dry_run:
            entry["status"] = "DOWNLOADED_ONLY"
            print(f"  {day.date()}  downloaded -> {csv_name}")
            results.append(entry)
            time.sleep(1.0)
            continue

        try:
            res = import_ohlcv_bytes(csv_bytes, csv_name, "NSE_BHAVCOPY", f"manual_inputs/nse/auto/{csv_name}")
            entry["status"] = "IMPORTED"
            entry["result"] = res
            print(f"  {day.date()}  imported: inserted={res.get('inserted')} "
                  f"dup={res.get('rows_duplicates')} conflicts={res.get('rows_conflicts')} "
                  f"accepted={res.get('rows_accepted')} invalid={res.get('rows_invalid')} "
                  f"unmapped={res.get('rows_unmapped')} ignored={res.get('rows_ignored')}")
        except Exception as e:
            entry["status"] = "IMPORT_FAILED"
            entry["error"] = str(e)
            print(f"  {day.date()}  IMPORT_FAILED: {e}")

        results.append(entry)
        time.sleep(1.0)

    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", nargs="*", default=None,
                     help="NSE symbols to fetch (default: every symbol in Stock Master)")
    ap.add_argument("--to", dest="date_to", default=None, help="Per-symbol end date DD-MM-YYYY (default: today)")
    ap.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                     help=f"Used only when a symbol has no existing history (default {DEFAULT_LOOKBACK_DAYS})")
    ap.add_argument("--bhavcopy-from", default=None, help=f"Bhavcopy start date DD-MM-YYYY (default: {DEFAULT_BHAVCOPY_LOOKBACK_DAYS} days ago)")
    ap.add_argument("--bhavcopy-to", default=None, help="Bhavcopy end date DD-MM-YYYY (default: today)")
    ap.add_argument("--skip-symbols", action="store_true", help="Skip the per-symbol historical fetch")
    ap.add_argument("--skip-bhavcopy", action="store_true", help="Skip the daily bhavcopy fetch")
    ap.add_argument("--dry-run", action="store_true", help="Download and save files only; do not import")
    ap.add_argument("--no-backup", action="store_true", help="Skip the pre-import DB backup (not recommended)")
    ap.add_argument(
        "--confirm-production",
        action="store_true",
        help="Required for a write run when DATABASE_URL points at data/swing_trading.db",
    )
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now()
    date_to = args.date_to or today.strftime("%d-%m-%Y")

    do_symbols = not args.skip_symbols
    do_bhavcopy = not args.skip_bhavcopy
    target_db = configured_db_path()
    is_production = os.path.normcase(str(target_db)) == os.path.normcase(str(PROD_DB.resolve()))

    if not args.dry_run and is_production and not args.confirm_production:
        print("REFUSED: production import requires --confirm-production. No download or database write was attempted.")
        return 3
    if not args.dry_run and is_production and args.no_backup:
        print("REFUSED: --no-backup is not permitted for production imports.")
        return 3

    backup_path = None
    if (do_symbols or do_bhavcopy) and not args.dry_run and not args.no_backup:
        backup_path = backup_database(target_db)
        print(f"Backup written: {backup_path}")

    results: list[dict] = []
    if do_bhavcopy:
        results += run_bhavcopy(args, today)
    if do_symbols:
        results += run_symbols(args, today, date_to)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    report_path = OUT_DIR / f"auto_download_report_{stamp}.json"
    report_path.write_text(json.dumps({
        "generated_at": stamp,
        "dry_run": args.dry_run,
        "database_path": str(target_db),
        "production_database": is_production,
        "backup_path": str(backup_path) if backup_path else None,
        "results": results,
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nReport written: {report_path}")

    failures = [r for r in results if r["status"] not in ("IMPORTED", "DOWNLOADED_ONLY", "NO_FILE", "UP_TO_DATE")]
    if failures:
        print(f"\n{len(failures)} of {len(results)} item(s) did not complete successfully -- see report.")
        return 2
    print(f"\nAll {len(results)} item(s) completed successfully (or had no file to fetch, e.g. weekends).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
