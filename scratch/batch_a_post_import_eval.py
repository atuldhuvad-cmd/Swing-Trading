"""Post-import evidence pipeline for Nifty 50 Batch A using application services."""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text
from app.database import SessionLocal
from app.models import (
    StockMaster, DailyOhlcv, CandidateEvaluationRun, CandidateCriterionResult,
    RiskRewardResult, FundamentalSnapshot,
)
from app.services.corporate_action_service import CorporateActionService
from app.services.technical_service import TechnicalService
from app.services.candidate_service import CandidateService
from app.services.fundamental_service import FundamentalService
from app.services.risk_reward_service import RiskRewardService

SYMBOLS = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BEL", "BHARTIARTL",
]
EXPECTED = {
    "ADANIENT": 247, "ADANIPORTS": 247, "APOLLOHOSP": 247, "ASIANPAINT": 247,
    "AXISBANK": 247, "BAJAJ-AUTO": 247, "BAJAJFINSV": 247, "BAJFINANCE": 247,
    "BEL": 247, "BHARTIARTL": 246,
}

# Application engine config: technical presence from genuine OHLCV; fundamentals
# are mandatory and must remain UNKNOWN when no snapshot exists.
CANDIDATE_CONFIG = {
    "name": "batch_a_post_import_evidence_gate",
    "criteria": [
        {"id": "SMA20", "type": "TECHNICAL", "operator": ">", "threshold": 0, "mandatory": True},
        {"id": "SMA50", "type": "TECHNICAL", "operator": ">", "threshold": 0, "mandatory": True},
        {"id": "SMA200", "type": "TECHNICAL", "operator": ">", "threshold": 0, "mandatory": True},
        {"id": "RSI14", "type": "TECHNICAL", "operator": ">=", "threshold": 0, "mandatory": True},
        {"id": "MACD", "type": "TECHNICAL", "operator": ">=", "threshold": -1000000, "mandatory": True},
        {"id": "ATR14", "type": "TECHNICAL", "operator": ">", "threshold": 0, "mandatory": True},
        {"id": "ROC20", "type": "TECHNICAL", "operator": ">=", "threshold": -1000000, "mandatory": True},
        {"id": "Liquidity20", "type": "TECHNICAL", "operator": ">", "threshold": 0, "mandatory": True},
        {"id": "revenue", "type": "FUNDAMENTAL", "operator": ">", "threshold": 0, "mandatory": True},
    ],
}
RR_CONFIG = {"atr_multiplier": 1.5, "buffer_percent": 0.01}


def rr_would_complete(tech: dict, entry: Decimal) -> bool:
    atr = tech.get("ATR14")
    support = tech.get("Support20")
    resistance = tech.get("Resistance20")
    if atr is None or support is None or resistance is None:
        return False
    stop = entry - (Decimal(str(atr)) * Decimal("1.5"))
    target = Decimal(str(resistance)) * Decimal("0.99")
    if not (stop > 0 and stop < entry):
        return False
    if not (target > entry):
        return False
    return True


def main():
    conn = sqlite3.connect(r"D:\Swing Trading\data\swing_trading.db")
    n = conn.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0]
    syn = conn.execute(
        """SELECT COUNT(*) FROM daily_ohlcv
           WHERE open=100 AND high=105 AND low=95 AND close=102 AND volume=1000"""
    ).fetchone()[0]
    per = dict(conn.execute(
        """SELECT s.nse_symbol, COUNT(*) FROM daily_ohlcv d
           JOIN stock_master s ON s.stock_id=d.stock_id GROUP BY s.nse_symbol"""
    ))
    print("OHLCV_TOTAL", n)
    print("SYNTHETIC_PATTERN", syn)
    print("PER_SYMBOL", per)
    print("INTEGRITY", conn.execute("PRAGMA integrity_check").fetchone()[0])
    print("FK", conn.execute("PRAGMA foreign_key_check").fetchall())
    if n != 2469 or syn != 0 or per != EXPECTED:
        raise SystemExit("STOP_OHLCV_GATE")
    before_runs = conn.execute("SELECT COUNT(*) FROM candidate_evaluation_run").fetchone()[0]
    before_crit = conn.execute("SELECT COUNT(*) FROM candidate_criterion_result").fetchone()[0]
    print("RUNS_BEFORE", before_runs, "CRIT_BEFORE", before_crit)
    conn.close()

    db = SessionLocal()
    reports = []
    try:
        for symbol in SYMBOLS:
            stock = db.query(StockMaster).filter(StockMaster.nse_symbol == symbol).one()
            raw = (
                db.query(DailyOhlcv)
                .filter(DailyOhlcv.stock_id == stock.stock_id, DailyOhlcv.series == "EQ")
                .order_by(DailyOhlcv.trading_date.asc())
                .all()
            )
            originals = [(r.open, r.high, r.low, r.close, r.volume) for r in raw]
            adjusted = CorporateActionService.apply_adjustments(db, stock.stock_id, raw)
            after = [(r.open, r.high, r.low, r.close, r.volume) for r in raw]
            if originals != after:
                raise RuntimeError(f"Raw OHLCV mutated for {symbol}")
            if any(o == 100 and h == 105 and l == 95 and c == 102 for o, h, l, c, v in originals):
                raise RuntimeError(f"Synthetic OHLC detected for {symbol}")

            tech = TechnicalService.calculate_technical_evidence(adjusted)
            snap = FundamentalService.get_latest_snapshot(db, stock.stock_id)
            if snap:
                fund = FundamentalService.get_metric_evidence(db, snap.snapshot_id)
                fund_state = f"PRESENT entity={snap.entity_type}"
            else:
                fund = {}
                fund_state = "UNKNOWN / INSUFFICIENT_DATA (no stored snapshot)"

            tech_for_eval = {k: tech.get(k) for k in [
                "SMA20", "SMA50", "SMA200", "RSI14", "MACD", "MACD_signal", "MACD_hist",
                "ATR14", "ATR_percent", "ROC20", "Liquidity20",
            ]}
            runs_before_stock = db.query(CandidateEvaluationRun).filter_by(stock_id=stock.stock_id).count()
            run = CandidateService.evaluate_candidate(
                db, stock.stock_id, CANDIDATE_CONFIG, tech_for_eval, fund,
                technical_ref=f"prod_ohlcv_{symbol}_{len(raw)}",
                fundamental_ref=snap.snapshot_id if snap else None,
            )
            db.flush()
            if db.query(CandidateEvaluationRun).filter_by(stock_id=stock.stock_id).count() != runs_before_stock + 1:
                raise RuntimeError("Evaluation overwrite detected")

            criteria = (
                db.query(CandidateCriterionResult)
                .filter_by(evaluation_id=run.evaluation_id)
                .order_by(CandidateCriterionResult.criterion_identifier)
                .all()
            )
            crit_summary = [
                f"{c.criterion_identifier}:{c.state}:{c.reason or ''}" for c in criteria
            ]
            reasons = [c.reason for c in criteria if c.state in ("UNKNOWN", "FAIL", "NOT_APPLICABLE")]
            reason = "; ".join(r for r in reasons if r) or "All configured criteria passed with stored evidence"

            rr_state = "NOT_COMPUTED (insufficient genuine evidence)"
            close = tech.get("latest_close")
            if close is not None and rr_would_complete(tech, Decimal(str(close))):
                rr = RiskRewardService.calculate_risk_reward(
                    db, run.evaluation_id, RR_CONFIG, tech, float(close)
                )
                db.flush()
                if rr.risk_reward_ratio is None:
                    db.delete(rr)
                    db.flush()
                    rr_state = "INSUFFICIENT (computed incomplete; not forced)"
                else:
                    rr_state = f"RR={rr.risk_reward_ratio} entry={rr.entry_reference} stop={rr.stop_loss} target={rr.target}"
            reports.append({
                "symbol": symbol,
                "sessions": tech.get("sessions"),
                "SMA200": str(tech.get("SMA200")),
                "RSI14": str(tech.get("RSI14")),
                "MACD": str(tech.get("MACD")),
                "MACD_signal": str(tech.get("MACD_signal")),
                "MACD_hist": str(tech.get("MACD_hist")),
                "ATR14": str(tech.get("ATR14")),
                "ATR_percent": str(tech.get("ATR_percent")),
                "ROC20": str(tech.get("ROC20")),
                "Breakout20": tech.get("Breakout20_status"),
                "Liquidity20": str(tech.get("Liquidity20")),
                "SMA20": str(tech.get("SMA20")),
                "SMA50": str(tech.get("SMA50")),
                "fund_state": fund_state,
                "classification": run.classification,
                "rr_state": rr_state,
                "reason": reason,
                "criteria": crit_summary,
                "evaluation_id": run.evaluation_id,
                "latest_close": str(close),
                "latest_date": str(tech.get("latest_trading_date")),
                "adjustment": tech.get("adjustment_status"),
            })

        # Preservation proof: rerun ADANIENT, old row must remain
        first = reports[0]["evaluation_id"]
        stock = db.query(StockMaster).filter_by(nse_symbol="ADANIENT").one()
        CandidateService.evaluate_candidate(
            db, stock.stock_id, CANDIDATE_CONFIG, {}, {},
            technical_ref="preservation_rerun",
        )
        db.commit()
        still = db.get(CandidateEvaluationRun, first)
        n_adani = db.query(CandidateEvaluationRun).filter_by(stock_id=stock.stock_id).count()
        print("PRESERVE_FIRST_RUN", still is not None, "classification", still.classification)
        print("ADANI_RUNS", n_adani)
        if still is None or n_adani < 2:
            raise SystemExit("STOP_HISTORY_OVERWRITE")
    finally:
        db.close()

    for r in reports:
        print("STOCK", json.dumps(r, default=str))
    totals = Counter(r["classification"] for r in reports)
    print("TOTALS", dict(totals))

    conn = sqlite3.connect(r"D:\Swing Trading\data\swing_trading.db")
    print("RUNS_AFTER", conn.execute("SELECT COUNT(*) FROM candidate_evaluation_run").fetchone()[0])
    print("INTEGRITY_AFTER", conn.execute("PRAGMA integrity_check").fetchone()[0])
    print("FK_AFTER", conn.execute("PRAGMA foreign_key_check").fetchall())
    print("OHLCV_AFTER", conn.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0])
    conn.close()


if __name__ == "__main__":
    main()
