"""Auto-download ICICI Direct's public stock recommendations (discovery only).

On-demand tool -- you run it whenever you want to check ICICI Direct's public
research page for new/updated calls on stocks you track. It does NOT write
to the database. It:

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

Deliberately does NOT create or supersede any BrokerRecommendation row.
Two reasons: this parser's real-world reliability against ICICI's actual
page markup is unverified (see the note below), and turning a scraped row
into a database entry means picking a verification_status and confirming
stock identity -- judgment calls your app's existing Recommendation Entry
screen is built for. Review the "actionable" list and enter/supersede
through /recommendations/new as usual (same as your existing 5 ICICI
entries) -- this script just does the finding, not the deciding.

Usage:
  venv\\Scripts\\python.exe ..\\scratch\\auto_download_broker_recs_icici.py

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
import re
import sys
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

from app.database import SessionLocal  # noqa: E402
from app.models import StockMaster, BrokerMaster, BrokerRecommendation, RatingNormalization  # noqa: E402

ICICI_URL = "https://www.icicidirect.com/research/equity/investing-ideas"
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


def write_report(stamp: str, *, status: str, error: str | None = None,
                 raw_html: str | None = None, total_rows: int = 0,
                 actionable: list | None = None, already_recorded: list | None = None,
                 unmatched: list | None = None) -> Path:
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
    }, indent=2, default=str), encoding="utf-8")
    return report_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-confidence", type=float, default=0.8,
                     help="Minimum name-match confidence (0-1) to list a row as actionable (default 0.8)")
    args = ap.parse_args()

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
    used = {c for c in (stock_col, cmp_col, target_col, date_col) if c}
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

            best_stock, best_score = None, 0.0
            for s in stocks:
                score = match_confidence(scraped_name, s.company_name)
                if score > best_score:
                    best_stock, best_score = s, score

            record = {
                "scraped_name": scraped_name,
                "rating": rating_raw,
                "normalized_rating": rating_map.get(rating_raw.lower()),
                "cmp": cmp_val,
                "target": target_val,
                "date": date_raw,
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

    report_path = write_report(
        stamp, status="OK", raw_html=str(raw_path), total_rows=len(table),
        actionable=actionable, already_recorded=already_recorded, unmatched=unmatched,
    )

    print(f"\n{len(actionable)} row(s) matched to a tracked stock and NOT already in your database:")
    for r in actionable:
        print(f"  {r['matched_symbol']:<12} {r['normalized_rating'] or r['rating']:<6} "
              f"target={r['target']} date={r['date']} (confidence={r['match_confidence']})")
    print(f"\n{len(already_recorded)} row(s) matched a tracked stock but you already have this exact "
          f"date's recommendation recorded (nothing to do).")
    print(f"\n{len(unmatched)} row(s) skipped (not a confident match to your tracked universe).")
    print(f"\nFull report: {report_path}")
    print("Nothing was imported -- review 'actionable' rows above and enter them via "
          "the Recommendation Entry screen (/recommendations/new) as usual, citing "
          f"{ICICI_URL} as the source with today's date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
