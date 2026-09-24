"""OHLCV catch-up acceptance helper.

Driven by scratch/ohlcv_catchup_acceptance.ps1. Safety model:

* Production (data/swing_trading.db) is only ever opened read-only through a
  SQLite ``mode=ro`` URI, and its SHA-256 is checked before and after.
* Database writes happen only through ``OhlcvService.confirm_import`` (via
  ``auto_download_ohlcv.import_ohlcv_bytes``) against the disposable database
  selected by ``DATABASE_URL``, and only after the resolved path has been
  verified to be that disposable database and not production.
* No row is ever inserted with direct SQL. No candidate evaluation is run.

Every subcommand writes a JSON result and exits non-zero when a required
check fails.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import sys
import zipfile
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
PROD_DB = (ROOT / "data" / "swing_trading.db").resolve()
AUTO_SCRIPT = ROOT / "scratch" / "auto_download_ohlcv.py"

TABLES = [
    "daily_ohlcv",
    "fundamental_snapshot",
    "candidate_evaluation_run",
    "candidate_criterion_result",
    "risk_reward_result",
    "broker_recommendation",
    "data_import_batch",
    "trade_journal",
]

BASELINE = {
    "sha256": "5de2603571b7587851ad1cb14426eec9a387878d05b7f80124f44068a579d54d",
    "counts": {
        "daily_ohlcv": 5446,
        "fundamental_snapshot": 20,
        "candidate_evaluation_run": 70,
        "candidate_criterion_result": 630,
        "risk_reward_result": 53,
        "broker_recommendation": 9,
        "data_import_batch": 109,
        "trade_journal": 0,
    },
    "latest_ohlcv_date": "2026-09-23",
}

# Same definition the earlier Batch A/B forensic scripts use.
SYNTHETIC_SQL = (
    "SELECT COUNT(*) FROM daily_ohlcv "
    "WHERE open=100 AND high=105 AND low=95 AND close=102 AND volume=1000"
)

UDIFF_REQUIRED = {
    "TradDt", "TckrSymb", "SctySrs", "OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol",
}

# Minimum sessions for each indicator in TechnicalService.
INDICATOR_MIN_SESSIONS = {
    "SMA20": 20,
    "SMA50": 50,
    "SMA200": 200,
    "RSI14": 15,
    "MACD": 26,
    "MACD_signal": 34,
    "MACD_hist": 34,
    "ATR14": 15,
    "ATR_percent": 15,
    "ROC20": 21,
    "Breakout20_threshold": 21,
    "Breakout20_status": 21,
    "Liquidity20": 20,
}


# --------------------------------------------------------------------------- utils

def norm(p) -> str:
    return os.path.normcase(str(Path(p).resolve()))


def is_prod(p) -> bool:
    return norm(p) == norm(PROD_DB)


def sha256_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def ro_connect(p) -> sqlite3.Connection:
    return sqlite3.connect(f"{Path(p).resolve().as_uri()}?mode=ro", uri=True)


def write_json(path, data) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def finish(out_path, data, failures) -> int:
    data["failures"] = failures
    data["result"] = "PASS" if not failures else "FAIL"
    write_json(out_path, data)
    print(f"[{data['result']}] {out_path}")
    for f in failures:
        print(f"  FAIL: {f}")
    return 0 if not failures else 1


def tracked_symbols(db_path) -> list[str]:
    with closing(ro_connect(db_path)) as c:
        return [r[0] for r in c.execute("SELECT nse_symbol FROM stock_master ORDER BY nse_symbol")]


def resolved_app_db() -> Path:
    """Resolve the database exactly as the application/automation script does."""
    sys.path.insert(0, str(BACKEND))
    from app.config import settings  # noqa: E402

    prefix = "sqlite:///"
    if not settings.database_url.startswith(prefix) or ":memory:" in settings.database_url:
        raise RuntimeError(f"Unexpected DATABASE_URL form: {settings.database_url!r}")
    return Path(settings.database_url[len(prefix):]).resolve()


def require_disposable(expect: str) -> Path:
    resolved = resolved_app_db()
    print(f"Resolved application database: {resolved}")
    if is_prod(resolved):
        raise SystemExit("REFUSED: application database resolves to PRODUCTION")
    if norm(resolved) != norm(expect):
        raise SystemExit(f"REFUSED: resolved database {resolved} != expected {expect}")
    from app.schema_readiness import guard_script_write
    guard_script_write(resolved)  # the disposable database's real migration state, before any write
    return resolved


# ------------------------------------------------------------------- snapshot

def snapshot(db_path) -> dict:
    p = Path(db_path).resolve()
    sha_before = sha256_file(p)
    out: dict = {"path": str(p), "sha256": sha_before, "is_production": is_prod(p)}
    with closing(ro_connect(p)) as c:
        out["counts"] = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
        latest = c.execute("SELECT MAX(trading_date) FROM daily_ohlcv").fetchone()[0]
        out["latest_ohlcv_date"] = (latest or "")[:10]
        out["synthetic_ohlcv"] = c.execute(SYNTHETIC_SQL).fetchone()[0]
        out["rows_linked_to_invalidated_synthetic_batches"] = c.execute(
            "SELECT COUNT(*) FROM daily_ohlcv d JOIN data_import_batch b "
            "ON b.import_batch_id=d.import_batch_id WHERE b.status='INVALIDATED_SYNTHETIC'"
        ).fetchone()[0]
        out["integrity"] = [r[0] for r in c.execute("PRAGMA integrity_check")]
        out["fk_violations"] = len(c.execute("PRAGMA foreign_key_check").fetchall())
        out["duplicate_canonical_keys"] = c.execute(
            "SELECT COUNT(*) FROM (SELECT stock_id, substr(trading_date,1,10) d, series, COUNT(*) n "
            "FROM daily_ohlcv GROUP BY 1,2,3 HAVING n>1)"
        ).fetchone()[0]
        out["invalid_ohlc"] = c.execute(
            "SELECT COUNT(*) FROM daily_ohlcv WHERE open<=0 OR high<=0 OR low<=0 OR close<=0 "
            "OR low>open OR low>close OR high<open OR high<close OR high<low"
        ).fetchone()[0]
        out["negative_volume"] = c.execute(
            "SELECT COUNT(*) FROM daily_ohlcv WHERE volume<0"
        ).fetchone()[0]
        out["max_import_batch_id"] = c.execute(
            "SELECT MAX(import_batch_id) FROM data_import_batch"
        ).fetchone()[0]
        per = {}
        for sym, n, mx in c.execute(
            "SELECT s.nse_symbol, COUNT(d.daily_ohlcv_id), MAX(d.trading_date) FROM stock_master s "
            "LEFT JOIN daily_ohlcv d ON d.stock_id=s.stock_id GROUP BY s.stock_id ORDER BY s.nse_symbol"
        ):
            per[sym] = {"sessions": n, "latest": (mx or "")[:10] or None}
        out["per_symbol"] = per
        digests = {}
        for row in c.execute(
            "SELECT daily_ohlcv_id, stock_id, trading_date, series, open, high, low, close, volume, "
            "source_name, import_batch_id FROM daily_ohlcv ORDER BY daily_ohlcv_id"
        ):
            digests[str(row[0])] = sha256_bytes(repr(row[1:]).encode())[:24]
        out["row_digests"] = digests
    sha_after = sha256_file(p)
    out["sha256_unchanged_by_read"] = sha_before == sha_after
    return out


def cmd_snapshot(a) -> int:
    snap = snapshot(a.db)
    failures = []
    if not snap["sha256_unchanged_by_read"]:
        failures.append("database file changed while being read")
    return finish(a.out, snap, failures)


def cmd_verify_prod(a) -> int:
    snap = snapshot(PROD_DB)
    failures = []
    if snap["sha256"] != BASELINE["sha256"]:
        failures.append(f"production SHA-256 {snap['sha256']} != baseline {BASELINE['sha256']}")
    for t, n in BASELINE["counts"].items():
        if snap["counts"][t] != n:
            failures.append(f"production {t}={snap['counts'][t]} != baseline {n}")
    if snap["latest_ohlcv_date"] != BASELINE["latest_ohlcv_date"]:
        failures.append(f"production latest OHLCV {snap['latest_ohlcv_date']} != {BASELINE['latest_ohlcv_date']}")
    if snap["synthetic_ohlcv"] != 0:
        failures.append(f"synthetic OHLCV rows: {snap['synthetic_ohlcv']}")
    if snap["integrity"] != ["ok"]:
        failures.append(f"integrity_check: {snap['integrity']}")
    if snap["fk_violations"] != 0:
        failures.append(f"foreign_key_check rows: {snap['fk_violations']}")
    if not snap["sha256_unchanged_by_read"]:
        failures.append("production changed while being read")
    snap.pop("row_digests", None)
    return finish(a.out, snap, failures)


# --------------------------------------------------------------------- backup

def cmd_backup(a) -> int:
    dest = Path(a.dest).resolve()
    failures = []
    if is_prod(dest):
        raise SystemExit("REFUSED: backup destination is production")
    if dest.exists():
        raise SystemExit(f"REFUSED: destination already exists: {dest}")
    if norm(dest).startswith(norm(ROOT)):
        raise SystemExit("REFUSED: disposable database must live outside the project folder")
    prod_sha_before = sha256_file(PROD_DB)
    with closing(ro_connect(PROD_DB)) as src, closing(sqlite3.connect(dest)) as dst:
        src.backup(dst)
    prod_sha_after = sha256_file(PROD_DB)
    prod = snapshot(PROD_DB)
    copy = snapshot(dest)
    if prod_sha_before != prod_sha_after:
        failures.append("production changed during backup")
    if copy["counts"] != prod["counts"]:
        failures.append(f"copy counts {copy['counts']} != production {prod['counts']}")
    if copy["integrity"] != ["ok"]:
        failures.append(f"copy integrity: {copy['integrity']}")
    if copy["fk_violations"] != 0:
        failures.append(f"copy FK violations: {copy['fk_violations']}")
    if copy["row_digests"] != prod["row_digests"]:
        failures.append("copy OHLCV rows differ from production")
    data = {
        "disposable_db": str(dest),
        "production_sha256_before": prod_sha_before,
        "production_sha256_after": prod_sha_after,
        "copy_sha256": copy["sha256"],
        "copy_sha_equals_production": copy["sha256"] == prod["sha256"],
        "production_counts": prod["counts"],
        "copy_counts": copy["counts"],
        "copy_integrity": copy["integrity"],
        "copy_fk_violations": copy["fk_violations"],
    }
    return finish(a.out, data, failures)


def cmd_resolve_db(a) -> int:
    resolved = resolved_app_db()
    failures = []
    if is_prod(resolved):
        failures.append("DATABASE_URL resolves to PRODUCTION")
    if norm(resolved) != norm(a.expect):
        failures.append(f"resolved {resolved} != expected {Path(a.expect).resolve()}")
    return finish(a.out, {
        "database_url": os.environ.get("DATABASE_URL"),
        "resolved_path": str(resolved),
        "expected_path": str(Path(a.expect).resolve()),
        "production_path": str(PROD_DB),
    }, failures)


# ------------------------------------------------------------ bhavcopy checks

def _num(v):
    try:
        return float((v or "").replace(",", "").strip())
    except ValueError:
        return None


def inspect_bhavcopy(zip_path: Path, csv_path: Path, day: str, tracked: list[str]) -> tuple[dict, list[str]]:
    fails: list[str] = []
    info: dict = {"date": day, "zip": zip_path.name, "csv": csv_path.name}
    zb = zip_path.read_bytes()
    cb = csv_path.read_bytes()
    info["zip_sha256"] = sha256_bytes(zb)
    info["csv_sha256"] = sha256_bytes(cb)
    info["zip_bytes"] = len(zb)
    info["zip_signature_ok"] = zb[:4] == b"PK\x03\x04"
    if not info["zip_signature_ok"]:
        fails.append(f"{day}: zip signature {zb[:8]!r} is not PK\\x03\\x04")
        return info, fails
    lead = zb[:64].lstrip().lower()
    if lead.startswith(b"<") or lead.startswith(b"{"):
        fails.append(f"{day}: archive looks like HTML/JSON")
    try:
        with zipfile.ZipFile(io.BytesIO(zb)) as zf:
            bad = zf.testzip()
            members = zf.namelist()
            csv_members = [n for n in members if n.lower().endswith(".csv")]
            info["members"] = members
            if bad:
                fails.append(f"{day}: corrupt zip member {bad}")
            if len(csv_members) != 1:
                fails.append(f"{day}: expected exactly one CSV member, found {csv_members}")
            else:
                inner = zf.read(csv_members[0])
                info["member_matches_saved_csv"] = inner == cb
                if inner != cb:
                    fails.append(f"{day}: saved CSV differs from archive member")
            for n in members:
                if "slb" in n.lower():
                    fails.append(f"{day}: Quote-SLB member {n}")
                if "BhavCopy_NSE_CM" not in n:
                    fails.append(f"{day}: unexpected member name {n}")
    except zipfile.BadZipFile as e:
        fails.append(f"{day}: bad zip: {e}")
        return info, fails

    text = cb.decode("utf-8-sig", errors="strict")
    head = text[:200].lstrip()
    if head.startswith("<") or head.startswith("{") or "captcha" in text[:4000].lower():
        fails.append(f"{day}: CSV content looks like HTML/JSON/CAPTCHA")
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = headers
    info["udiff_structure"] = UDIFF_REQUIRED.issubset(headers)
    if not info["udiff_structure"]:
        fails.append(f"{day}: missing UDiFF columns {sorted(UDIFF_REQUIRED - set(headers))}")
        return info, fails
    info["quote_slb_headers"] = any("settlement date" in h.lower() or "settlement_date" in h.lower() for h in headers)
    if info["quote_slb_headers"]:
        fails.append(f"{day}: Quote-SLB style headers present")

    tracked_set = set(tracked)
    physical = eq = 0
    series_counts: dict[str, int] = {}
    dates = set()
    tracked_rows: dict[str, dict] = {}
    tracked_other_series: dict[str, list[str]] = {}
    tracked_invalid = []
    tracked_dupes = []
    for row in reader:
        if not any((v or "").strip() for v in row.values()):
            continue
        physical += 1
        sym = (row.get("TckrSymb") or "").strip()
        ser = (row.get("SctySrs") or "").strip()
        dates.add((row.get("TradDt") or "").strip())
        series_counts[ser] = series_counts.get(ser, 0) + 1
        if ser != "EQ":
            if sym in tracked_set:
                tracked_other_series.setdefault(sym, []).append(ser)
            continue
        eq += 1
        if sym not in tracked_set:
            continue
        o, h, l, c = (_num(row.get(k)) for k in ("OpnPric", "HghPric", "LwPric", "ClsPric"))
        v = _num(row.get("TtlTradgVol"))
        if sym in tracked_rows:
            tracked_dupes.append(sym)
        tracked_rows[sym] = {"open": o, "high": h, "low": l, "close": c, "volume": v}
        if None in (o, h, l, c, v) or min(o, h, l, c) <= 0 or v < 0 or not (l <= o <= h and l <= c <= h):
            tracked_invalid.append(sym)
    info.update({
        "physical_rows": physical,
        "eq_rows": eq,
        "non_eq_rows": physical - eq,
        "series_top": dict(sorted(series_counts.items(), key=lambda kv: -kv[1])[:8]),
        "trade_dates_in_file": sorted(dates),
        "tracked_eq_present": sorted(tracked_rows),
        "tracked_missing_eq": sorted(tracked_set - set(tracked_rows)),
        "tracked_missing_eq_other_series": {s: tracked_other_series.get(s, []) for s in sorted(tracked_set - set(tracked_rows))},
        "tracked_invalid": tracked_invalid,
        "tracked_duplicate_keys_in_file": tracked_dupes,
    })
    if dates != {day}:
        fails.append(f"{day}: TradDt values {sorted(dates)} do not match file date")
    if eq == 0:
        fails.append(f"{day}: no EQ rows")
    if tracked_invalid:
        fails.append(f"{day}: invalid tracked OHLCV {tracked_invalid}")
    if tracked_dupes:
        fails.append(f"{day}: duplicate tracked keys in file {tracked_dupes}")
    return info, fails


def cmd_validate_downloads(a) -> int:
    report = read_json(a.report)
    evid = Path(a.evidence)
    files_dir = evid / "dryrun_files"
    files_dir.mkdir(parents=True, exist_ok=True)
    tracked = tracked_symbols(PROD_DB)
    failures: list[str] = []
    days: list[dict] = []
    if report.get("dry_run") is not True:
        failures.append("report is not a dry-run report")
    # Negative control: the application's own guard must reject a Quote-SLB file.
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    sys.path.insert(0, str(BACKEND))
    from app.services.ohlcv_service import OhlcvService  # noqa: E402
    slb_guard = OhlcvService._is_quote_slb("Quote-SLB-sample.csv", ["Symbol"]) and \
        OhlcvService._is_quote_slb("x.csv", ["Settlement Date"])
    if not slb_guard:
        failures.append("application Quote-SLB guard did not reject the negative control")
    for r in report.get("results", []):
        if r.get("kind") != "bhavcopy":
            continue
        day = r["date"]
        wd = datetime.strptime(day, "%Y-%m-%d").strftime("%A")
        entry = {"date": day, "weekday": wd, "status": r["status"]}
        if r["status"] == "DOWNLOADED_ONLY":
            zp, cp = Path(r["saved_zip"]), Path(r["saved_csv"])
            info, fails = inspect_bhavcopy(zp, cp, day, tracked)
            entry.update(info)
            failures += fails
            shutil.copy2(zp, files_dir / zp.name)
            shutil.copy2(cp, files_dir / cp.name)
        elif r["status"] == "NO_FILE":
            entry["note"] = "weekend" if wd in ("Saturday", "Sunday") else \
                "weekday without file: exchange holiday or not yet published"
        else:
            failures.append(f"{day}: {r['status']} {r.get('error')}")
            entry["error"] = r.get("error")
        days.append(entry)
    available = [d["date"] for d in days if d["status"] == "DOWNLOADED_ONLY"]
    expected_increase = {s: 0 for s in tracked}
    for d in days:
        for s in d.get("tracked_eq_present", []):
            expected_increase[s] += 1
    data = {
        "report": a.report,
        "report_production_database_flag": report.get("production_database"),
        "quote_slb_guard_negative_control": slb_guard,
        "tracked_symbols": tracked,
        "available_trading_dates": available,
        "no_file_dates": [(d["date"], d["weekday"]) for d in days if d["status"] == "NO_FILE"],
        "expected_session_increase": expected_increase,
        "days": days,
    }
    return finish(a.out, data, failures)


# --------------------------------------------------------------- import check

def _metrics(res: dict) -> dict:
    return {
        "import_batch_id": res.get("import_batch_id"),
        "file_sha256": res.get("file_sha256"),
        "non_eq_ignored": res.get("rows_ignored"),
        "mapped_accepted": res.get("rows_accepted"),
        "invalid_eq": res.get("rows_invalid"),
        "unmapped": res.get("rows_unmapped"),
        "duplicates": res.get("rows_duplicates"),
        "conflicts": res.get("rows_conflicts"),
        "inserted": res.get("inserted"),
    }


def cmd_check_import(a) -> int:
    rep = read_json(a.report)
    dry = read_json(a.dryrun)
    evid = Path(a.evidence)
    files_dir = evid / "import_files"
    files_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    expect = Path(a.expect).resolve()
    if rep.get("dry_run") is not False:
        failures.append("import report dry_run is not false")
    if rep.get("production_database") is not False:
        failures.append(f"import report production_database={rep.get('production_database')}")
    if norm(rep.get("database_path", "")) != norm(expect):
        failures.append(f"report database_path {rep.get('database_path')} != {expect}")
    bp = rep.get("backup_path")
    backup_ok = bool(bp) and norm(Path(bp).parent) == norm(expect.parent) and Path(bp).exists()
    if not backup_ok:
        failures.append(f"backup_path {bp} is not an existing file in {expect.parent}")
    backup_integrity = None
    if backup_ok:
        with closing(ro_connect(bp)) as c:
            backup_integrity = [r[0] for r in c.execute("PRAGMA integrity_check")]
        if backup_integrity != ["ok"]:
            failures.append(f"backup integrity {backup_integrity}")

    dry_days = {d["date"]: d for d in dry["days"]}
    per_date = []
    for r in rep.get("results", []):
        if r.get("kind") != "bhavcopy":
            continue
        day = r["date"]
        row = {"date": day, "status": r["status"]}
        dd = dry_days.get(day, {})
        if r["status"] == "IMPORTED":
            res = r["result"]
            csv_path = Path(r["saved_csv"])
            content = csv_path.read_bytes()
            shutil.copy2(csv_path, files_dir / csv_path.name)
            row.update(_metrics(res))
            row["physical_rows"] = dd.get("physical_rows")
            row["eq_rows"] = dd.get("eq_rows")
            row["csv_sha256_on_disk"] = sha256_bytes(content)
            row["csv_sha256_matches_dry_run"] = dd.get("csv_sha256") == row["csv_sha256_on_disk"]
            if row["csv_sha256_on_disk"] != res.get("file_sha256"):
                failures.append(f"{day}: saved CSV SHA differs from imported file_sha256")
            if not row["csv_sha256_matches_dry_run"]:
                failures.append(f"{day}: imported CSV differs from dry-run download (NSE file changed?)")
            if dd.get("status") != "DOWNLOADED_ONLY":
                failures.append(f"{day}: imported but dry run status was {dd.get('status')}")
            if res.get("rows_conflicts"):
                failures.append(f"{day}: conflicts={res.get('rows_conflicts')}")
            tracked_present = len(dd.get("tracked_eq_present", []))
            if res.get("inserted", 0) + res.get("rows_duplicates", 0) != tracked_present:
                failures.append(
                    f"{day}: inserted+duplicates={res.get('inserted', 0) + res.get('rows_duplicates', 0)} "
                    f"!= tracked EQ rows in file {tracked_present}"
                )
            if dd.get("tracked_invalid"):
                failures.append(f"{day}: invalid tracked rows {dd.get('tracked_invalid')}")
        elif r["status"] == "NO_FILE":
            if dd.get("status") != "NO_FILE":
                failures.append(f"{day}: NO_FILE on import run but {dd.get('status')} on dry run")
        else:
            failures.append(f"{day}: {r['status']} {r.get('error')}")
        per_date.append(row)
    total_inserted = sum((p.get("inserted") or 0) for p in per_date)
    data = {
        "report": a.report,
        "production_database": rep.get("production_database"),
        "database_path": rep.get("database_path"),
        "backup_path": bp,
        "backup_integrity": backup_integrity,
        "total_inserted": total_inserted,
        "per_date": per_date,
    }
    return finish(a.out, data, failures)


# --------------------------------------------------------------------- compare

def cmd_compare(a) -> int:
    before = read_json(a.before)
    after = read_json(a.after)
    failures: list[str] = []
    data: dict = {"mode": a.mode, "before": a.before, "after": a.after}
    for key in ("integrity", "fk_violations", "duplicate_canonical_keys", "invalid_ohlc",
                "negative_volume", "synthetic_ohlcv"):
        data[f"after_{key}"] = after[key]
    if after["integrity"] != ["ok"]:
        failures.append(f"integrity {after['integrity']}")
    for key in ("fk_violations", "duplicate_canonical_keys", "invalid_ohlc", "negative_volume", "synthetic_ohlcv"):
        if after[key] != 0:
            failures.append(f"{key}={after[key]}")
    data["count_delta"] = {t: after["counts"][t] - before["counts"][t] for t in TABLES}
    for t in TABLES:
        if t in ("daily_ohlcv", "data_import_batch"):
            continue
        if data["count_delta"][t] != 0:
            failures.append(f"{t} changed by {data['count_delta'][t]}")
    b_dig, a_dig = before["row_digests"], after["row_digests"]
    changed = [k for k, v in b_dig.items() if a_dig.get(k) != v]
    data["pre_existing_rows_changed_or_missing"] = len(changed)
    if changed:
        failures.append(f"{len(changed)} pre-existing OHLCV rows changed or missing (e.g. {changed[:5]})")

    if a.mode == "import":
        imp = read_json(a.import_check)
        dry = read_json(a.dryrun)
        if data["count_delta"]["daily_ohlcv"] != imp["total_inserted"]:
            failures.append(
                f"daily_ohlcv delta {data['count_delta']['daily_ohlcv']} != reported inserted {imp['total_inserted']}"
            )
        imported_days = [p for p in imp["per_date"] if p["status"] == "IMPORTED"]
        if data["count_delta"]["data_import_batch"] != len(imported_days):
            failures.append(
                f"data_import_batch delta {data['count_delta']['data_import_batch']} != imported files {len(imported_days)}"
            )
        available = dry["available_trading_dates"]
        last_available = max(available) if available else None
        per = {}
        for sym, exp in dry["expected_session_increase"].items():
            b, af = before["per_symbol"].get(sym, {}), after["per_symbol"].get(sym, {})
            inc = af.get("sessions", 0) - b.get("sessions", 0)
            per[sym] = {
                "latest_before": b.get("latest"), "latest_after": af.get("latest"),
                "sessions_before": b.get("sessions"), "sessions_after": af.get("sessions"),
                "increase": inc, "expected_increase": exp,
            }
            if inc != exp:
                failures.append(f"{sym}: session increase {inc} != sessions present in files {exp}")
        for d in dry["days"]:
            for sym in d.get("tracked_missing_eq", []):
                per.setdefault(sym, {}).setdefault("missing_available_sessions", [])
                if d["date"] not in per[sym]["missing_available_sessions"]:
                    per[sym]["missing_available_sessions"].append(d["date"])
                per[sym].setdefault("other_series_in_file", {})[d["date"]] = \
                    d.get("tracked_missing_eq_other_series", {}).get(sym, [])
        data["last_available_session"] = last_available
        data["per_symbol"] = per
    elif a.mode == "replay":
        if data["count_delta"]["daily_ohlcv"] != 0:
            failures.append(f"replay changed daily_ohlcv by {data['count_delta']['daily_ohlcv']}")
        if set(a_dig) != set(b_dig):
            failures.append("replay changed the set of OHLCV rows")
        data["new_audit_batches"] = data["count_delta"]["data_import_batch"]
    return finish(a.out, data, failures)


# ---------------------------------------------------------------------- replay

def cmd_replay(a) -> int:
    require_disposable(a.expect)
    imp = read_json(a.import_check)
    files_dir = Path(a.files)
    spec = importlib.util.spec_from_file_location("auto_download_ohlcv", AUTO_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from app.database import SessionLocal  # noqa: E402
    from app.services.ohlcv_service import OhlcvService  # noqa: E402

    if is_prod(mod.configured_db_path()):
        raise SystemExit("REFUSED: automation module resolves to production")

    failures: list[str] = []
    per_date = []
    for prior in [x for x in imp["per_date"] if x["status"] == "IMPORTED"]:
        day = prior["date"]
        name = f"BhavCopy_NSE_CM_0_0_0_{day.replace('-', '')}_F_0000.csv"
        content = (files_dir / name).read_bytes()
        if sha256_bytes(content) != prior["file_sha256"]:
            failures.append(f"{day}: replay file SHA differs from the imported file")
        db = SessionLocal()
        try:
            preview = OhlcvService.parse_historical_file(db, content, name)
            statuses: dict[str, int] = {}
            for r in preview.preview_rows:
                statuses[r.status] = statuses.get(r.status, 0) + 1
        finally:
            db.rollback()
            db.close()
        res = mod.import_ohlcv_bytes(content, name, "NSE_BHAVCOPY", f"manual_inputs/nse/auto/{name}")
        row = {"date": day, "preview_status_counts": statuses, **_metrics(res)}
        expected_dupes = (prior.get("inserted") or 0) + (prior.get("duplicates") or 0)
        if res.get("inserted") != 0:
            failures.append(f"{day}: replay inserted {res.get('inserted')}")
        if res.get("rows_conflicts"):
            failures.append(f"{day}: replay conflicts {res.get('rows_conflicts')}")
        if res.get("rows_duplicates") != expected_dupes:
            failures.append(f"{day}: replay duplicates {res.get('rows_duplicates')} != {expected_dupes}")
        per_date.append(row)
    return finish(a.out, {"per_date": per_date}, failures)


# ------------------------------------------------------------------- technical

def cmd_technical(a) -> int:
    resolved = require_disposable(a.expect)
    dry = read_json(a.dryrun)
    last_available = max(dry["available_trading_dates"]) if dry["available_trading_dates"] else None
    sha_before = sha256_file(resolved)
    from app.database import SessionLocal  # noqa: E402
    from app.models import StockMaster  # noqa: E402
    from app.services.evidence_service import EvidenceService  # noqa: E402

    failures: list[str] = []
    out = {}
    db = SessionLocal()
    try:
        for s in db.query(StockMaster).order_by(StockMaster.nse_symbol).all():
            t = EvidenceService.technical_for_stock(db, s.stock_id)
            ind = t["indicators"]
            sessions = t["sessions"]
            missing = [k for k, n in INDICATOR_MIN_SESSIONS.items() if sessions >= n and ind.get(k) is None]
            not_ready = [k for k, n in INDICATOR_MIN_SESSIONS.items() if sessions < n]
            out[s.nse_symbol] = {
                "sessions": sessions,
                "latest_trading_date": (t.get("latest_trading_date") or "")[:10] or None,
                "adjustment_status": t.get("adjustment_status"),
                "insufficient_history_for": not_ready,
                "indicators": {k: ind.get(k) for k in INDICATOR_MIN_SESSIONS},
            }
            if missing:
                failures.append(f"{s.nse_symbol}: indicators null despite enough history: {missing}")
            if sessions and last_available and out[s.nse_symbol]["latest_trading_date"] != last_available:
                out[s.nse_symbol]["note"] = f"latest session is not the last available session {last_available}"
    finally:
        db.rollback()
        db.close()
    sha_after = sha256_file(resolved)
    if sha_before != sha_after:
        failures.append("technical readiness check modified the disposable database")
    return finish(a.out, {
        "database": str(resolved),
        "last_available_session": last_available,
        "database_unchanged_by_check": sha_before == sha_after,
        "per_symbol": out,
    }, failures)


# ----------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("verify-prod"); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_verify_prod)
    p = sub.add_parser("snapshot"); p.add_argument("--db", required=True); p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_snapshot)
    p = sub.add_parser("backup"); p.add_argument("--dest", required=True); p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_backup)
    p = sub.add_parser("resolve-db"); p.add_argument("--expect", required=True); p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_resolve_db)
    p = sub.add_parser("validate-downloads")
    p.add_argument("--report", required=True); p.add_argument("--evidence", required=True)
    p.add_argument("--out", required=True); p.set_defaults(fn=cmd_validate_downloads)
    p = sub.add_parser("check-import")
    for k in ("--report", "--dryrun", "--expect", "--evidence", "--out"):
        p.add_argument(k, required=True)
    p.set_defaults(fn=cmd_check_import)
    p = sub.add_parser("compare")
    p.add_argument("--mode", choices=["import", "replay"], required=True)
    for k in ("--before", "--after", "--out"):
        p.add_argument(k, required=True)
    p.add_argument("--import-check"); p.add_argument("--dryrun")
    p.set_defaults(fn=cmd_compare)
    p = sub.add_parser("replay")
    for k in ("--expect", "--import-check", "--files", "--out"):
        p.add_argument(k, required=True)
    p.set_defaults(fn=cmd_replay)
    p = sub.add_parser("technical")
    for k in ("--expect", "--dryrun", "--out"):
        p.add_argument(k, required=True)
    p.set_defaults(fn=cmd_technical)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
