"""Verify downloaded Batch B NSE cash-market exports. Read-only: no imports, no DB writes."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
DB = ROOT / "data" / "swing_trading.db"
SRC = ROOT / "manual_inputs" / "nse" / "Nifty50"
OUT_DIR = ROOT / "manual_inputs" / "batch_b"

BATCH_B = ["CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
           "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO"]
MIN_SESSIONS = 200
EXPECTED = {
    "daily_ohlcv": 2469, "candidate_evaluation_run": 33, "candidate_criterion_result": 297,
    "risk_reward_result": 29, "fundamental_snapshot": 10, "broker_recommendation": 5,
}
DATE_FORMATS = ("%d-%b-%Y", "%Y-%m-%d", "%d-%B-%Y", "%d/%m/%Y")


def production_state() -> dict:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        s = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in EXPECTED}
        s["synthetic_ohlcv"] = conn.execute(
            "SELECT COUNT(*) FROM daily_ohlcv WHERE open=100 AND high=105 AND low=95 AND close=102 AND volume=1000"
        ).fetchone()[0]
        s["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
        s["fk_violations"] = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        conn.close()
    return s


def parse_date(raw: str):
    raw = (raw or "").strip().strip('"')
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def classify(path: Path) -> dict:
    """Classify a CSV and, when it is a genuine single-symbol cash-market export, measure it."""
    name = path.name
    content = path.read_bytes()
    info: dict = {
        "filename": name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
    }

    if "quote-slb" in name.lower().replace(" ", ""):
        return {**info, "kind": "REJECTED", "reason": "Quote-SLB securities-lending data, not equity OHLCV"}

    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="replace")))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = headers

    if any("settlement date" in h.lower() or "settlement_date" in h.lower() for h in headers):
        return {**info, "kind": "REJECTED", "reason": "Settlement-date header indicates Quote-SLB data"}
    if "Symbol" not in headers:
        return {**info, "kind": "REJECTED", "reason": f"No Symbol column; headers={headers[:6]}"}
    if "Date" not in headers:
        return {**info, "kind": "REJECTED",
                "reason": "No Date column - reference/constituent list, not price history"}

    def num(raw):
        try:
            return float((raw or "").replace(",", "").strip().strip('"'))
        except (ValueError, AttributeError):
            return None

    def col(row, *names):
        for n in names:
            for key in row:
                if key and key.strip().lower() == n:
                    return row[key]
        return None

    physical = non_eq = invalid_eq = 0
    eq_dates: list = []
    symbols: set[str] = set()
    series_counts: dict[str, int] = defaultdict(int)
    bad_ohlc = bad_volume = 0

    for row in reader:
        physical += 1
        sym = (row.get("Symbol") or "").strip().strip('"').upper()
        series = (row.get("Series") or "").strip().strip('"').upper()
        if sym:
            symbols.add(sym)
        series_counts[series or "(blank)"] += 1
        if series != "EQ":
            non_eq += 1
            continue
        d = parse_date(row.get("Date") or "")
        if d is None:
            invalid_eq += 1
            continue
        eq_dates.append(d)

        o = num(col(row, "open price", "open"))
        h = num(col(row, "high price", "high"))
        lo = num(col(row, "low price", "low"))
        c = num(col(row, "close price", "close"))
        v = num(col(row, "total traded quantity", "volume", "ttl trd qnty"))
        if None in (o, h, lo, c) or min(o, h, lo, c) <= 0 or h < lo or h < max(o, c) or lo > min(o, c):
            bad_ohlc += 1
        if v is None or v < 0:
            bad_volume += 1

    info.update({
        "physical_rows": physical,
        "eq_rows": len(eq_dates) + invalid_eq,
        "non_eq_filtered": non_eq,
        "invalid_eq": invalid_eq,
        "symbols": sorted(symbols),
        "series_counts": dict(series_counts),
        "invalid_ohlc_rows": bad_ohlc,
        "invalid_volume_rows": bad_volume,
    })

    if len(symbols) > 1:
        return {**info, "kind": "REJECTED",
                "reason": f"Multi-symbol reference file ({len(symbols)} symbols) - not a single-stock export"}
    if not eq_dates:
        return {**info, "kind": "REJECTED", "reason": "No valid EQ rows with parseable trading dates"}

    unique = sorted(set(eq_dates))
    info.update({
        "kind": "CASH_MARKET",
        "symbol": next(iter(symbols)) if symbols else None,
        "unique_sessions": len(unique),
        "duplicate_sessions": len(eq_dates) - len(unique),
        "earliest": str(unique[0]),
        "latest": str(unique[-1]),
        "span_months": round((unique[-1] - unique[0]).days / 30.44, 1),
    })
    return info


def main() -> None:
    before = production_state()

    if not SRC.exists():
        raise SystemExit(f"Source directory missing: {SRC}")

    files = sorted(SRC.glob("*.csv"))
    results = [classify(p) for p in files]
    rejected = [r for r in results if r["kind"] == "REJECTED"]
    cash = [r for r in results if r["kind"] == "CASH_MARKET"]

    print(f"=== DIRECTORY: {SRC} ===")
    print(f"CSV files present: {len(files)} | genuine single-symbol cash-market: {len(cash)} | rejected: {len(rejected)}")

    print("\n=== REJECTED FILES ===")
    if not rejected:
        print("  none")
    for r in rejected:
        print(f"  {r['filename']:<52} {r['reason']}")

    print("\n=== PER-SYMBOL VERIFICATION ===")
    rows = []
    for symbol in BATCH_B:
        matches = [c for c in cash if c["symbol"] == symbol]
        if not matches:
            rows.append({"symbol": symbol, "status": "MISSING - USER DOWNLOAD REQUIRED",
                         "filename": None, "unique_sessions": 0, "ge_200": False, "sma200_ready": False})
            print(f"\n{symbol}\n  Status: MISSING - no genuine cash-market export present")
            continue

        best = max(matches, key=lambda c: c["unique_sessions"])
        others = [m["filename"] for m in matches if m["filename"] != best["filename"]]
        ge200 = best["unique_sessions"] >= MIN_SESSIONS
        status = "READY" if ge200 else (
            f"INSUFFICIENT - {best['unique_sessions']} sessions "
            f"({MIN_SESSIONS - best['unique_sessions']} short)")
        row = {
            "symbol": symbol, "filename": best["filename"], "symbol_identity": best["symbol"],
            "identity_ok": best["symbol"] == symbol,
            "date_range": f"{best['earliest']} to {best['latest']}",
            "span_months": best["span_months"], "physical_rows": best["physical_rows"],
            "eq_rows": best["eq_rows"], "non_eq_filtered": best["non_eq_filtered"],
            "invalid_eq": best["invalid_eq"], "unique_sessions": best["unique_sessions"],
            "duplicate_sessions": best["duplicate_sessions"], "ge_200": ge200,
            "sma200_ready": ge200, "sha256": best["sha256"],
            "invalid_ohlc_rows": best["invalid_ohlc_rows"],
            "invalid_volume_rows": best["invalid_volume_rows"],
            "series_counts": best["series_counts"],
            "overlapping_not_merged": others, "status": status,
        }
        if best["invalid_ohlc_rows"] or best["invalid_volume_rows"]:
            row["status"] = (f"REJECTED - {best['invalid_ohlc_rows']} bad OHLC row(s), "
                             f"{best['invalid_volume_rows']} bad volume row(s)")
            row["ge_200"] = row["sma200_ready"] = False
        rows.append(row)
        print(f"\n{symbol}")
        print(f"  Filename        : {row['filename']}")
        print(f"  Symbol identity : {row['symbol_identity']}  (match: {row['identity_ok']})")
        print(f"  Date range      : {row['date_range']}  ({row['span_months']} months)")
        print(f"  Physical rows   : {row['physical_rows']}")
        print(f"  EQ rows         : {row['eq_rows']}")
        print(f"  Non-EQ filtered : {row['non_eq_filtered']}")
        print(f"  Invalid EQ rows : {row['invalid_eq']}")
        print(f"  Unique sessions : {row['unique_sessions']}")
        print(f"  Duplicate sess. : {row['duplicate_sessions']}")
        print(f"  Series breakdown: {row['series_counts']}")
        print(f"  Invalid OHLC    : {row['invalid_ohlc_rows']}")
        print(f"  Invalid volume  : {row['invalid_volume_rows']}")
        print(f"  >=200           : {row['ge_200']}")
        print(f"  SMA200-ready    : {row['sma200_ready']}")
        print(f"  SHA-256         : {row['sha256']}")
        print(f"  Status          : {row['status']}")
        if others:
            print(f"  Overlapping (NOT merged): {others}")

    # Inspect Downloads for candidate files. Report only; never move or copy.
    print("\n=== DOWNLOADS INSPECTION (report only, nothing moved) ===")
    downloads = Path(r"C:\Users\dhuva\Downloads")
    staged: list[dict] = []
    if not downloads.exists():
        print(f"  {downloads} does not exist")
    else:
        dl_csvs = list(downloads.rglob("*.csv"))
        print(f"  {downloads}: {len(dl_csvs)} CSV file(s)")
        for p in dl_csvs:
            try:
                info = classify(p)
            except Exception as exc:
                print(f"    UNREADABLE {p}: {exc}")
                continue
            sym = info.get("symbol")
            if info["kind"] == "CASH_MARKET" and sym in BATCH_B:
                staged.append({**info, "path": str(p)})
                print(f"    BATCH B CANDIDATE: {p}")
                print(f"      symbol={sym} sessions={info['unique_sessions']} "
                      f"range={info['earliest']}..{info['latest']} sha={info['sha256'][:16]}")
        if not staged:
            print("    No Batch B cash-market exports found in Downloads.")

    after = production_state()
    ready = sum(1 for r in rows if r["status"] == "READY")
    located = sum(1 for r in rows if r["filename"])

    print("\n=== SUMMARY ===")
    print(f"Files required : {len(BATCH_B)}")
    print(f"Files located  : {located}")
    print(f"Files valid    : {ready}")
    print(f"Stocks >=200   : {ready}")
    print(f"SMA200-ready   : {ready}")
    print(f"Insufficient   : {sum(1 for r in rows if str(r['status']).startswith('INSUFFICIENT'))}")
    print(f"Rejected files : {len(rejected)}")
    print(f"Awaiting user move from Downloads: {len(staged)}")
    for s in staged:
        print(f"  {s['path']}  (symbol={s['symbol']}, sessions={s['unique_sessions']})")
    print("PRODUCTION_BEFORE", json.dumps(before))
    print("PRODUCTION_AFTER ", json.dumps(after))
    print("PRODUCTION_DRIFT", json.dumps({k: (before[k], after[k]) for k in before if before[k] != after[k]}))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"batch_b_download_verification_{stamp}.json"
    out.write_text(json.dumps({
        "generated_at": stamp, "source_dir": str(SRC), "rows": rows,
        "rejected": rejected, "downloads_candidates": staged,
        "production_before": before, "production_after": after,
    }, indent=2), encoding="utf-8")
    print("REPORT", out)


if __name__ == "__main__":
    main()
