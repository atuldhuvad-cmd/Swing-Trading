"""READ-ONLY Batch B technical evidence audit.

Uses the existing EvidenceService/TechnicalService pipeline (corporate-action adjusted).
The ORM session is rolled back and never committed. Nothing is persisted: no candidate
evaluations, no RR rows, no configuration changes.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
DB = ROOT / "data" / "swing_trading.db"
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal
from app.models import StockMaster, FundamentalSnapshot, FundamentalMetric
from app.services.evidence_service import EvidenceService

SYMBOLS = ["CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
           "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO"]

COUNT_TABLES = ["daily_ohlcv", "stock_master", "fundamental_snapshot",
                "candidate_evaluation_run", "candidate_criterion_result",
                "risk_reward_result", "broker_recommendation", "data_import_batch"]


def production_state() -> dict:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    state = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in COUNT_TABLES}
    state["synthetic_ohlcv"] = conn.execute(
        "SELECT COUNT(*) FROM daily_ohlcv WHERE open=100 AND high=105 AND low=95 "
        "AND close=102 AND volume=1000").fetchone()[0]
    state["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
    state["fk_violations"] = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    conn.close()
    state["db_sha256"] = hashlib.sha256(DB.read_bytes()).hexdigest()
    return state


def dec(value):
    return None if value is None else float(value)


def main() -> None:
    before = production_state()
    print("PRODUCTION_BEFORE", json.dumps(before))

    db = SessionLocal()
    rows = []
    try:
        for sym in SYMBOLS:
            stock = db.query(StockMaster).filter(StockMaster.nse_symbol == sym).one()
            tech = EvidenceService.technical_for_stock(db, stock.stock_id)
            ind = tech["indicators"]

            close = dec(tech.get("latest_close"))
            sma50 = dec(ind.get("SMA50"))
            sma200 = dec(ind.get("SMA200"))

            snapshots = db.query(FundamentalSnapshot).filter(
                FundamentalSnapshot.stock_id == stock.stock_id).all()
            revenue_known = False
            for snap in snapshots:
                metrics = db.query(FundamentalMetric).filter(
                    FundamentalMetric.snapshot_id == snap.snapshot_id,
                    FundamentalMetric.metric_name == "revenue").all()
                if any(m.metric_value is not None for m in metrics):
                    revenue_known = True

            # Technical portion of the Phase 5 policy only. Not a production classification.
            required = {"SMA20": ind.get("SMA20"), "SMA50": ind.get("SMA50"),
                        "SMA200": ind.get("SMA200"), "ATR14": ind.get("ATR14")}
            missing = [k for k, v in required.items() if v is None]
            if tech["sessions"] < 200:
                missing.append("sessions>=200")
            if close is None:
                missing.append("latest_close")

            if missing:
                potential = "POTENTIAL_INSUFFICIENT"
            elif close <= sma50:
                potential = "POTENTIAL_REJECTED"
            elif sma200 is not None and sma50 > sma200:
                potential = "POTENTIAL_FINAL"
            else:
                potential = "POTENTIAL_WATCH"

            rows.append({
                "symbol": sym, "stock_id": stock.stock_id,
                "sessions": tech["sessions"],
                "sma200_ready": tech["sma200_ready"],
                "latest_trading_date": str(tech.get("latest_trading_date"))[:10],
                "close": close,
                "SMA20": dec(ind.get("SMA20")), "SMA50": sma50, "SMA200": sma200,
                "close_gt_sma50": None if (close is None or sma50 is None) else close > sma50,
                "sma50_gt_sma200": None if (sma50 is None or sma200 is None) else sma50 > sma200,
                "RSI14": dec(ind.get("RSI14")),
                "MACD": dec(ind.get("MACD")), "MACD_signal": dec(ind.get("MACD_signal")),
                "MACD_hist": dec(ind.get("MACD_hist")),
                "ATR14": dec(ind.get("ATR14")), "ATR_percent": dec(ind.get("ATR_percent")),
                "ROC20": dec(ind.get("ROC20")),
                "Breakout20_status": ind.get("Breakout20_status"),
                "Breakout20_threshold": dec(ind.get("Breakout20_threshold")),
                "Support20": dec(ind.get("Support20")),
                "Resistance20": dec(ind.get("Resistance20")),
                "Liquidity20": dec(ind.get("Liquidity20")),
                "adjustment_status": tech.get("adjustment_status"),
                "revenue_evidence": "KNOWN" if revenue_known else "UNKNOWN",
                "missing_technical_evidence": missing,
                "potential_technical_only": potential,
            })
    finally:
        db.rollback()
        db.close()

    print("\n=== PER-SYMBOL TECHNICAL EVIDENCE (corporate-action adjusted) ===")
    for r in rows:
        print(f"\n{r['symbol']}  (stock_id={r['stock_id']})")
        print(f"  sessions={r['sessions']}  latest={r['latest_trading_date']}  close={r['close']}")
        print(f"  SMA20={r['SMA20']}  SMA50={r['SMA50']}  SMA200={r['SMA200']}")
        print(f"  close>SMA50={r['close_gt_sma50']}  SMA50>SMA200={r['sma50_gt_sma200']}")
        print(f"  RSI14={r['RSI14']}  MACD={r['MACD']}  signal={r['MACD_signal']}  hist={r['MACD_hist']}")
        print(f"  ATR14={r['ATR14']}  ATR%={r['ATR_percent']}  ROC20={r['ROC20']}")
        print(f"  Breakout20={r['Breakout20_status']} (threshold {r['Breakout20_threshold']})  "
              f"Support20={r['Support20']}  Resistance20={r['Resistance20']}")
        print(f"  Liquidity20={r['Liquidity20']}  adjustment={r['adjustment_status']}")
        print(f"  revenue evidence={r['revenue_evidence']}  "
              f"potential(technical only)={r['potential_technical_only']}")

    buckets = {k: [r["symbol"] for r in rows if r["potential_technical_only"] == k]
               for k in ("POTENTIAL_FINAL", "POTENTIAL_WATCH", "POTENTIAL_REJECTED",
                         "POTENTIAL_INSUFFICIENT")}
    print("\n=== POTENTIAL (TECHNICAL PORTION ONLY - NOT PRODUCTION CLASSIFICATIONS) ===")
    for k, v in buckets.items():
        print(f"  {k:<24} {len(v)}  {v}")
    print("  SMA200-ready:", sum(1 for r in rows if r["sma200_ready"]), "/", len(rows))
    print("  revenue KNOWN:", sum(1 for r in rows if r["revenue_evidence"] == "KNOWN"), "/", len(rows))

    after = production_state()
    print("\nPRODUCTION_AFTER ", json.dumps(after))
    drift = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    print("PRODUCTION_DRIFT", json.dumps(drift) if drift else "NONE")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "manual_inputs" / "batch_b" / f"batch_b_technical_audit_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"generated_at": stamp, "rows": rows, "buckets": buckets,
                               "production_before": before, "production_after": after},
                              indent=2, default=str), encoding="utf-8")
    print("REPORT", out)
    if drift:
        raise SystemExit("STOP_PRODUCTION_WRITE_DETECTED")


if __name__ == "__main__":
    main()
