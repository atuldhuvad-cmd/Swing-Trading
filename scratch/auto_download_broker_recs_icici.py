"""Auto-download ICICI Direct's public stock recommendations, optionally auto-import them.

Default run is report-only (no database write). With --import it also records
new and changed calls for stocks you track, using the same recommendation
service the Recommendation Entry screen uses. Import rules (all must hold):

  * the row matches exactly one tracked stock with confidence >= 0.9;
  * the rating maps through rating_normalization and the call date is valid,
    not in the future and not older than 400 days;
  * a newer call for a stock that already has a CURRENT ICICI call supersedes
    it (history kept); an older or identical call is skipped;
  * evidence is stored as ICICI Direct's own website, VERIFIED_PRIMARY, with the
    report PDF link when the page has one -- the same shape as the entries made
    by hand from this page. The page's CMP is a live price, so it is kept in the
    evidence text only and is NOT stored as the price on the call date;
  * a run refuses to import if the page returned fewer than 20 rows or would
    create more than --max-imports (default 25) records;
  * a verified backup is taken first, and a production database additionally
    needs --confirm-production.

Rows for stocks you do not track, ambiguous name matches and anything failing a
rule are reported, never imported.

The description below is the report-only behaviour. It:

  1. Fetches https://www.icicidirect.com/research/equity/investing-ideas --
     ICICI Direct's own public "Investing Ideas" table (Buy/Hold/Sell calls,
     CMP, target, date). No login needed; robots.txt allows crawling this
     path (it explicitly disallows /mailcontent/* instead, which this script
     does not touch).
  2. Parses every row on the page (not just your tracked stocks).
  3. Matches each row's company name against your Stock Master by a
     tolerant name comparison (ICICI abbreviates names, e.g. "Hindalco
     Inds." for "Hindalco Industries Limited") -- every match is reported
     with its confidence, nothing is assumed silently.
  4. Cross-checks matched rows against your existing broker_recommendation
     table (same stock + ICICI Direct + same recommendation_date) to flag
     what's already there vs genuinely new/changed.
  5. Saves the full raw table (all rows, your universe or not) and a
     filtered "actionable" list to manual_inputs/broker_recommendations/,
     and prints a report.

Without --import it does NOT create or supersede any BrokerRecommendation row.

Usage:
  venv\\Scripts\\python.exe ..\\scratch\\auto_download_broker_recs_icici.py
  venv\\Scripts\\python.exe ..\\scratch\\auto_download_broker_recs_icici.py --import --confirm-production

VERIFICATION STATUS: unusual for this project -- I could not fetch this
page from ANY shell available while building this (icicidirect.com is
blocked from both this session's sandbox and its cloud container, same as
nseindia.com). The only view I had was through Claude's own web-reading
tool, which doesn't show raw HTML. BUT that view's data checked out
precisely against your own database: the 5 stocks currently in your
broker_recommendation table (CARYSIL, ASTRAMICRO, HINDALCO, GLAND,
NRBBEARING, all sourced from verified ICICI Direct PDFs per your README)
had their exact recommendation dates AND exact target prices reproduced by
the live page -- e.g. HINDALCO target 1,240.00 on 11-Aug-2026 in both your
DB and the live fetch, for all 5 stocks. That's strong evidence the data
itself is real and current. What's NOT verified is whether this specific
script's requests+pandas.read_html approach parses ICICI's actual page
markup correctly -- that could only be proven by actually running it. If
it fails to find any table, it prints the raw HTML's first 2000 characters
so you (or Claude, if you paste it back) can see what changed.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

import requests
from lxml import html as lxml_html

try:
    import pandas as pd
except ImportError:
    print("This script needs pandas (already added to backend/requirements.txt) "
          "and lxml (added alongside it) -- run pip install -r requirements.txt first.")
    raise

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "manual_inputs" / "broker_recommendations"
sys.path.insert(0, str(ROOT / "backend"))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    StockMaster, BrokerMaster, BrokerRecommendation, RatingNormalization, SourceTypeMaster,
)
from app.schemas.recommendation import BrokerRecommendationCreate, SourceReferenceCreate  # noqa: E402
from app.services.recommendation_service import RecommendationService  # noqa: E402
from app import schema_readiness  # noqa: E402

ICICI_URL = "https://www.icicidirect.com/research/equity/investing-ideas"
PROD_DB = ROOT / "data" / "swing_trading.db"
BROKER_NAME = "ICICI Securities"
SOURCE_TYPE_NAME = "BROKER_WEBSITE"
PUBLICATION_NAME = "ICICI Direct - Investing Ideas (website)"
MIN_PAGE_ROWS = 20
MAX_CALL_AGE_DAYS = 400
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_SUFFIX_WORDS = {
    "ltd", "limited", "inds", "industries", "co", "corp", "corpn", "company",
    "enterp", "enterprises", "engg", "engineering", "technologies", "technology",
    "labs", "laboratories", "pvt", "private", "india", "intl", "international",
}


def _normalize_name(name: str) -> list[str]:
    name = re.sub(r"[.,()&]", " ", name.lower())
    name = re.sub(r"'s\b", "", name)  # "Dr. Reddy's" -> "dr reddy"
    words = [w for w in name.split() if w and w not in _SUFFIX_WORDS]
    return words


def match_confidence(scraped_name: str, db_name: str) -> float:
    """0.0 (no match) to 1.0 (best match). Tolerant of ICICI's truncation
    (e.g. 'Hindalco Inds.' vs 'Hindalco Industries Limited') via prefix and
    token-overlap checks on normalized word lists."""
    a, b = _normalize_name(scraped_name), _normalize_name(db_name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Prefix matching is only safe when both names retain at least two words.
    # A one-word prefix produced dangerous collisions such as "Hind." with
    # Hindalco and "Astral" with Astra Microwave.
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) >= 2:
        prefix_ok = True
        for i, w in enumerate(shorter):
            if i >= len(longer):
                prefix_ok = False
                break
            lw = longer[i]
            exact_or_safe_prefix = lw == w or (
                min(len(lw), len(w)) >= 4 and (lw.startswith(w) or w.startswith(lw))
            )
            if not exact_or_safe_prefix:
                prefix_ok = False
                break
        if prefix_ok:
            return 0.9
    # fallback: token overlap
    sa, sb = set(a), set(b)
    overlap = len(sa & sb) / max(1, len(sa | sb))
    return overlap if overlap >= 0.5 else 0.0


def find_recommendation_table(html: str) -> "pd.DataFrame | None":
    try:
        tables = pd.read_html(io.StringIO(html))
    except ValueError:
        return None
    best = None
    for t in tables:
        cols = [str(c).strip().lower() for c in t.columns]
        blob = " ".join(cols)
        score = sum(k in blob for k in ("stock", "rating", "cmp", "target", "date"))
        if score >= 3 and len(t) > (len(best) if best is not None else 0):
            best = t
    return best


def extract_report_links(page_html: str) -> dict[str, str]:
    """Map the visible company name to its official ICICI report link.

    pandas intentionally flattens table cells and loses anchor hrefs, so the
    link is collected separately from the same source HTML for provenance.
    """
    links: dict[str, str] = {}
    try:
        root = lxml_html.fromstring(page_html)
    except (ValueError, TypeError):
        return links
    for row in root.xpath("//tr"):
        cells = row.xpath("./td")
        if not cells:
            continue
        company = " ".join(cells[0].text_content().split())
        pdf_links = row.xpath(".//a[contains(translate(@href, 'PDF', 'pdf'), '.pdf')]/@href")
        if company and pdf_links:
            links[company] = pdf_links[0]
    return links


def parse_rating_map(db) -> dict[str, str]:
    return {r.original_rating.strip().lower(): r.normalized_rating for r in db.query(RatingNormalization).all()}


def _num(value) -> float | None:
    """Float from a scraped cell, or None for blank/NaN/non-numeric."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def parse_call_date(value: str):
    try:
        return datetime.strptime(str(value).strip(), "%d %b %Y").date()
    except ValueError:
        return None


def configured_db_path() -> Path:
    prefix = "sqlite:///"
    if not settings.database_url.startswith(prefix) or ":memory:" in settings.database_url:
        raise RuntimeError("Automated recommendation import requires a file-backed SQLite database")
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


def evidence_text(record: dict, scraped_at: str) -> str:
    def rs(v):
        n = _num(v)
        return "n/a" if n is None else f"Rs {n:g}"
    return (
        f"ICICI Direct 'Investing Ideas' page, row for {record['scraped_name']}: "
        f"CMP {rs(record.get('cmp'))} (page price when collected {scraped_at}; live price, not the price on the call date), "
        f"Entry Price {rs(record.get('entry'))}, Target Price {rs(record.get('target'))}, "
        f"Stop Loss {rs(record.get('stop_loss'))}, Call Date {record.get('date')}, "
        f"Duration {record.get('duration') or 'n/a'}, Action: {record.get('rating')}."
    )


def build_recommendation(record: dict, *, stock_id: int, broker_id: int, source_type_id: int,
                         call_date, scraped_at: str) -> BrokerRecommendationCreate:
    entry = _num(record.get("entry"))
    return BrokerRecommendationCreate(
        stock_id=stock_id,
        broker_id=broker_id,
        recommendation_date=datetime.combine(call_date, datetime.min.time()),
        original_rating=record["rating"],
        normalized_rating=record["normalized_rating"],
        recommended_price=None,
        entry_price_low=entry,
        entry_price_high=entry,
        target_price=_num(record.get("target")),
        stop_loss=_num(record.get("stop_loss")),
        time_horizon_text=record.get("duration") or None,
        currency="INR",
        lifecycle_status="CURRENT",
        evidence=[SourceReferenceCreate(
            source_type_id=source_type_id,
            publication_name=PUBLICATION_NAME,
            url=record.get("source_reference") or ICICI_URL,
            source_date=datetime.combine(call_date, datetime.min.time()),
            original_text=evidence_text(record, scraped_at),
            verification_status="VERIFIED_PRIMARY",
            verification_notes=(
                "Auto-imported from ICICI Direct's own public page by "
                "auto_download_broker_recs_icici.py --import; collected " + scraped_at + "."
            ),
        )],
    )


def plan_import(db, records: list[dict], *, today, min_confidence: float = 0.9) -> list[dict]:
    """Decide, per scraped row, whether to CREATE, SUPERSEDE or SKIP. Writes nothing."""
    broker = db.query(BrokerMaster).filter(BrokerMaster.canonical_name == BROKER_NAME).first()
    source_type = db.query(SourceTypeMaster).filter(SourceTypeMaster.type_name == SOURCE_TYPE_NAME).first()
    if broker is None or source_type is None:
        raise RuntimeError(f"Broker '{BROKER_NAME}' and source type '{SOURCE_TYPE_NAME}' must exist before importing")

    plans: list[dict] = []
    for rec in records:
        plan = {"symbol": rec.get("matched_symbol"), "scraped_name": rec.get("scraped_name"),
                "date": rec.get("date"), "rating": rec.get("rating"), "target": _num(rec.get("target")),
                "action": "SKIP", "reason": None, "supersedes": None}
        plans.append(plan)

        def skip(reason: str):
            plan["reason"] = reason

        if not rec.get("matched_symbol"):
            skip("NOT_TRACKED")
            continue
        if rec.get("ambiguous"):
            skip("AMBIGUOUS_MATCH")
            continue
        if (rec.get("match_confidence") or 0) < min_confidence:
            skip("LOW_CONFIDENCE")
            continue
        if not rec.get("normalized_rating"):
            skip("UNMAPPED_RATING")
            continue
        call_date = parse_call_date(rec.get("date"))
        if call_date is None:
            skip("BAD_DATE")
            continue
        if call_date > today:
            skip("FUTURE_DATE")
            continue
        if (today - call_date).days > MAX_CALL_AGE_DAYS:
            skip("STALE_CALL")
            continue
        target = _num(rec.get("target"))
        if target is not None and target <= 0:
            skip("BAD_TARGET")
            continue
        entry = _num(rec.get("entry"))
        if entry is not None and entry <= 0:
            skip("BAD_ENTRY")
            continue
        stock = db.query(StockMaster).filter(StockMaster.nse_symbol == rec["matched_symbol"]).first()
        if stock is None:
            skip("NOT_TRACKED")
            continue

        current = (
            db.query(BrokerRecommendation)
            .filter(BrokerRecommendation.stock_id == stock.stock_id,
                    BrokerRecommendation.broker_id == broker.broker_id,
                    BrokerRecommendation.lifecycle_status == "CURRENT")
            .order_by(BrokerRecommendation.recommendation_date.desc(), BrokerRecommendation.recommendation_id.desc())
            .first()
        )
        plan.update({"stock_id": stock.stock_id, "broker_id": broker.broker_id,
                     "source_type_id": source_type.source_type_id, "call_date": call_date})
        if current is None:
            plan["action"] = "CREATE"
        elif current.recommendation_date.date() < call_date:
            plan["action"] = "SUPERSEDE"
            plan["supersedes"] = current.recommendation_id
        elif current.recommendation_date.date() == call_date:
            skip("ALREADY_RECORDED")
        else:
            skip("OLDER_THAN_RECORDED")
    return plans


def apply_import(db, plans: list[dict], records_by_key: dict, *, scraped_at: str) -> list[dict]:
    """Execute CREATE/SUPERSEDE plans through the app's RecommendationService."""
    results = []
    for plan in plans:
        result = {k: plan.get(k) for k in ("symbol", "date", "rating", "target", "action", "reason", "supersedes")}
        if plan["action"] == "SKIP":
            result["status"] = "SKIPPED"
            results.append(result)
            continue
        rec = records_by_key[(plan["symbol"], plan["date"])]
        payload = build_recommendation(
            rec, stock_id=plan["stock_id"], broker_id=plan["broker_id"],
            source_type_id=plan["source_type_id"], call_date=plan["call_date"], scraped_at=scraped_at,
        )
        try:
            if plan["action"] == "SUPERSEDE":
                new = RecommendationService.supersede_recommendation(db, plan["supersedes"], payload)
            else:
                new = RecommendationService.create_recommendation(db, payload)
            result["status"] = "IMPORTED"
            result["recommendation_id"] = new.recommendation_id
        except HTTPException as e:
            db.rollback()
            result["status"] = "SKIPPED_DUPLICATE" if e.status_code == 409 else "FAILED"
            result["detail"] = str(e.detail)
        results.append(result)
    return results


def write_report(stamp: str, *, status: str, error: str | None = None,
                 raw_html: str | None = None, total_rows: int = 0,
                 actionable: list | None = None, already_recorded: list | None = None,
                 unmatched: list | None = None, import_summary: dict | None = None) -> Path:
    report_path = OUT_DIR / f"icici_report_{stamp}.json"
    report_path.write_text(json.dumps({
        "generated_at": stamp,
        "status": status,
        "source_url": ICICI_URL,
        "error": error,
        "raw_html": raw_html,
        "total_rows": total_rows,
        "actionable": actionable or [],
        "already_recorded": already_recorded or [],
        "unmatched_or_untracked": unmatched or [],
        "import": import_summary,
    }, indent=2, default=str), encoding="utf-8")
    return report_path


def run_import(args, actionable: list[dict], page_rows: int, target_db: Path, is_production: bool,
               stamp: str) -> tuple[dict, int]:
    """Guards, backup, plan, apply, verify. Returns (summary for the report, exit code)."""
    summary: dict = {"requested": True, "database_path": str(target_db), "production_database": is_production,
                     "backup_path": None, "plans": [], "results": [], "refused": None}
    if page_rows < MIN_PAGE_ROWS:
        summary["refused"] = f"page returned only {page_rows} rows (< {MIN_PAGE_ROWS}); parser or page may be broken"
        print(f"IMPORT REFUSED: {summary['refused']}")
        return summary, 3

    refusal = schema_readiness.write_refusal(SessionLocal)  # read-only check, before planning, backup or write
    if refusal:
        summary["refused"] = refusal
        print(f"IMPORT {refusal}")
        return summary, 3

    db = SessionLocal()
    try:
        today = datetime.now().date()
        plans = plan_import(db, actionable, today=today, min_confidence=args.import_min_confidence)
        summary["plans"] = [{k: v for k, v in p.items() if k not in ("call_date",)} for p in plans]
        writes = [p for p in plans if p["action"] != "SKIP"]
        if len(writes) > args.max_imports:
            summary["refused"] = f"{len(writes)} records would be written (> --max-imports {args.max_imports})"
            print(f"IMPORT REFUSED: {summary['refused']}")
            return summary, 3
        if not writes:
            print("\nImport: nothing new to record.")
            return summary, 0

        backup_path = backup_database(target_db)
        summary["backup_path"] = str(backup_path)
        print(f"\nBackup written: {backup_path}")
        before = db.query(BrokerRecommendation).count()
        records_by_key = {(r["matched_symbol"], r["date"]): r for r in actionable}
        results = apply_import(db, plans, records_by_key, scraped_at=stamp)
        summary["results"] = results
        after = db.query(BrokerRecommendation).count()
        imported = [r for r in results if r["status"] == "IMPORTED"]
        failed = [r for r in results if r["status"] == "FAILED"]
        summary.update({"count_before": before, "count_after": after, "imported": len(imported),
                        "failed": len(failed)})
        integrity = db.execute(text("PRAGMA integrity_check")).fetchall()
        fk = db.execute(text("PRAGMA foreign_key_check")).fetchall()
        summary["integrity_ok"] = [tuple(r) for r in integrity] == [("ok",)] and not fk
        for r in imported:
            print(f"  IMPORTED {r['symbol']:<12} {r['rating']:<5} target={r['target']} date={r['date']}"
                  f"{' (supersedes #' + str(r['supersedes']) + ')' if r.get('supersedes') else ''}")
        if after - before != len(imported):
            summary["refused"] = f"count mismatch: {before} -> {after} but {len(imported)} imported"
            print(f"WARNING: {summary['refused']}")
            return summary, 2
        if failed or not summary["integrity_ok"]:
            print(f"WARNING: {len(failed)} record(s) failed / integrity ok={summary['integrity_ok']} -- see report.")
            return summary, 2
        return summary, 0
    finally:
        db.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-confidence", type=float, default=0.8,
                     help="Minimum name-match confidence (0-1) to list a row as actionable (default 0.8)")
    ap.add_argument("--import", dest="do_import", action="store_true",
                     help="Also record new/changed calls for tracked stocks (backup first)")
    ap.add_argument("--import-min-confidence", type=float, default=0.9,
                     help="Minimum name-match confidence required to import a row (default 0.9)")
    ap.add_argument("--max-imports", type=int, default=25,
                     help="Refuse to import if more than this many records would be written (default 25)")
    ap.add_argument("--confirm-production", action="store_true",
                     help="Required for --import when DATABASE_URL points at data/swing_trading.db")
    args = ap.parse_args()

    target_db = configured_db_path()
    is_production = os.path.normcase(str(target_db)) == os.path.normcase(str(PROD_DB.resolve()))
    if args.do_import and is_production and not args.confirm_production:
        print("REFUSED: --import on the production database requires --confirm-production. "
              "Nothing was downloaded or written.")
        return 3

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    try:
        resp = requests.get(ICICI_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        report_path = write_report(stamp, status="SOURCE_UNAVAILABLE", error=str(e))
        print(f"SOURCE_UNAVAILABLE: {e}")
        print(f"Failure report: {report_path}")
        print("Nothing was imported. Use the Broker Uploads screen for a verified official PDF while the source is unavailable.")
        return 1

    raw_path = OUT_DIR / f"icici_investing_ideas_{stamp}.html"
    raw_path.write_text(resp.text, encoding="utf-8")

    table = find_recommendation_table(resp.text)
    if table is None:
        report_path = write_report(
            stamp, status="PARSE_FAILED",
            error="No recommendation table found in the current page markup",
            raw_html=str(raw_path),
        )
        print("Could not find a recommendation table on the page -- ICICI's markup may have changed.")
        print(f"Raw HTML saved to {raw_path} -- first 2000 chars:")
        print(resp.text[:2000])
        print(f"Failure report: {report_path}")
        return 2

    table.columns = [str(c).strip() for c in table.columns]
    report_links = extract_report_links(resp.text)
    print(f"Parsed table: {len(table)} rows, columns: {list(table.columns)}")

    def col(*keywords, exclude=frozenset()):
        for c in table.columns:
            if c in exclude:
                continue
            cl = c.lower()
            if any(k in cl for k in keywords):
                return c
        return None

    # Real ICICI markup (confirmed 2026-09-03) has no column literally
    # named "Rating" -- it has "Call Date", and col("rating", "call")
    # used to match "Call Date" via the "call" substring, silently
    # duplicating the date into the rating field. rating_col is
    # informational only (matching/dedup below never uses it), so it is
    # resolved last, excluding columns already claimed, and is no longer
    # required for the script to proceed.
    stock_col = col("stock", "company")
    cmp_col = col("cmp")
    target_col = col("target")
    date_col = col("date", "reco")
    entry_col = col("entry")
    stop_col = col("stop")
    duration_col = col("duration", "horizon")
    used = {c for c in (stock_col, cmp_col, target_col, date_col, entry_col, stop_col, duration_col) if c}
    rating_col = col("rating", "recommendation", "action", "call type", exclude=used)

    if not stock_col or not target_col:
        report_path = write_report(
            stamp, status="PARSE_FAILED",
            error=f"Expected columns missing: {list(table.columns)}",
            raw_html=str(raw_path), total_rows=len(table),
        )
        print(f"Table is missing expected columns (got {list(table.columns)}) -- ICICI's markup may have changed.")
        print(f"Raw HTML saved to {raw_path}")
        print(f"Failure report: {report_path}")
        return 2
    if not rating_col:
        print("Note: no rating/action-like column found -- rating will be blank in the report; "
              "matching and already-recorded checks below do not depend on it.")

    db = SessionLocal()
    try:
        stocks = db.query(StockMaster).all()
        broker = db.query(BrokerMaster).filter(BrokerMaster.canonical_name == "ICICI Securities").first()
        rating_map = parse_rating_map(db)

        existing_dates = set()
        if broker:
            for rec in db.query(BrokerRecommendation).filter(BrokerRecommendation.broker_id == broker.broker_id).all():
                existing_dates.add((rec.stock_id, rec.recommendation_date.date() if rec.recommendation_date else None))

        actionable, already_recorded, unmatched = [], [], []
        for _, row in table.iterrows():
            scraped_name = str(row.get(stock_col, "")).strip()
            if not scraped_name or scraped_name.lower() == "nan":
                continue
            rating_raw = str(row.get(rating_col, "")).strip() if rating_col else ""
            cmp_val = row.get(cmp_col) if cmp_col else None
            target_val = row.get(target_col)
            date_raw = str(row.get(date_col, "")).strip() if date_col else ""

            best_stock, best_score, runner_up = None, 0.0, 0.0
            for s in stocks:
                score = match_confidence(scraped_name, s.company_name)
                if score > best_score:
                    best_stock, best_score, runner_up = s, score, best_score
                elif score > runner_up:
                    runner_up = score

            record = {
                "scraped_name": scraped_name,
                "rating": rating_raw,
                "normalized_rating": rating_map.get(rating_raw.lower()),
                "cmp": cmp_val,
                "target": target_val,
                "date": date_raw,
                "entry": row.get(entry_col) if entry_col else None,
                "stop_loss": row.get(stop_col) if stop_col else None,
                "duration": (str(row.get(duration_col, "")).strip() if duration_col else "") or None,
                "ambiguous": bool(best_stock and best_score >= args.min_confidence and runner_up >= best_score),
                "match_confidence": round(best_score, 2),
                "matched_symbol": best_stock.nse_symbol if best_stock and best_score >= args.min_confidence else None,
                "source_reference": report_links.get(scraped_name, ICICI_URL),
            }

            if best_stock and best_score >= args.min_confidence:
                try:
                    rec_date = datetime.strptime(date_raw, "%d %b %Y").date()
                except ValueError:
                    rec_date = None
                already = (best_stock.stock_id, rec_date) in existing_dates
                record["already_in_db"] = already
                if already:
                    already_recorded.append(record)
                else:
                    actionable.append(record)
            else:
                unmatched.append(record)

    finally:
        db.close()

    import_summary = None
    exit_code = 0
    if args.do_import:
        import_summary, exit_code = run_import(args, actionable, len(table), target_db, is_production, stamp)

    report_path = write_report(
        stamp, status="OK", raw_html=str(raw_path), total_rows=len(table),
        actionable=actionable, already_recorded=already_recorded, unmatched=unmatched,
        import_summary=import_summary,
    )

    print(f"\n{len(actionable)} row(s) matched to a tracked stock and NOT already in your database:")
    for r in actionable:
        print(f"  {r['matched_symbol']:<12} {r['normalized_rating'] or r['rating']:<6} "
              f"target={r['target']} date={r['date']} (confidence={r['match_confidence']})")
    print(f"\n{len(already_recorded)} row(s) matched a tracked stock but you already have this exact "
          f"date's recommendation recorded (nothing to do).")
    print(f"\n{len(unmatched)} row(s) skipped (not a confident match to your tracked universe).")
    print(f"\nFull report: {report_path}")
    if import_summary is None:
        print("Nothing was imported (report-only run). Re-run with --import to record these automatically.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
