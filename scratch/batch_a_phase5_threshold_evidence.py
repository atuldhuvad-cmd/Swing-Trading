"""Non-persistent Batch A technical distribution and Phase 5 rule simulation."""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal
from app.models import StockMaster, DailyOhlcv, RiskRewardResult, CandidateEvaluationRun
from app.services.corporate_action_service import CorporateActionService
from app.services.technical_service import TechnicalService
from app.services.evidence_service import EvidenceService

SYMBOLS = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BEL", "BHARTIARTL",
]


def D(v):
    return None if v is None else Decimal(str(v))


def main():
    db = SessionLocal()
    rows = []
    try:
        for symbol in SYMBOLS:
            stock = db.query(StockMaster).filter_by(nse_symbol=symbol).one()
            raw = (
                db.query(DailyOhlcv)
                .filter(DailyOhlcv.stock_id == stock.stock_id, DailyOhlcv.series == "EQ")
                .order_by(DailyOhlcv.trading_date.asc())
                .all()
            )
            tech = TechnicalService.calculate_technical_evidence(
                CorporateActionService.apply_adjustments(db, stock.stock_id, raw)
            )
            close = D(tech.get("latest_close"))
            sma20, sma50, sma200 = D(tech.get("SMA20")), D(tech.get("SMA50")), D(tech.get("SMA200"))
            macd, signal = D(tech.get("MACD")), D(tech.get("MACD_signal"))
            roc = D(tech.get("ROC20"))
            run = EvidenceService.latest_run(db, stock.stock_id)
            rr = None
            if run:
                rr_res = (
                    db.query(RiskRewardResult)
                    .filter(RiskRewardResult.evaluation_id == run.evaluation_id)
                    .order_by(RiskRewardResult.result_id.desc())
                    .first()
                )
                if rr_res:
                    rr = str(rr_res.risk_reward_ratio)
            rows.append({
                "symbol": symbol,
                "close": str(close),
                "SMA20": str(sma20),
                "SMA50": str(sma50),
                "SMA200": str(sma200),
                "close_gt_SMA20": bool(close is not None and sma20 is not None and close > sma20),
                "close_gt_SMA50": bool(close is not None and sma50 is not None and close > sma50),
                "close_gt_SMA200": bool(close is not None and sma200 is not None and close > sma200),
                "SMA20_gt_SMA50": bool(sma20 is not None and sma50 is not None and sma20 > sma50),
                "SMA50_gt_SMA200": bool(sma50 is not None and sma200 is not None and sma50 > sma200),
                "RSI14": str(tech.get("RSI14")),
                "MACD": str(macd),
                "MACD_signal": str(signal),
                "MACD_hist": str(tech.get("MACD_hist")),
                "MACD_gt_signal": bool(macd is not None and signal is not None and macd > signal),
                "ROC20": str(roc),
                "ROC20_gt_0": bool(roc is not None and roc > 0),
                "Breakout20": tech.get("Breakout20_status"),
                "Breakout20_threshold": str(tech.get("Breakout20_threshold")),
                "ATR_percent": str(tech.get("ATR_percent")),
                "Liquidity20": str(tech.get("Liquidity20")),
                "RR": rr,
                "complete": all(v is not None for v in [close, sma20, sma50, sma200, macd, signal, roc, tech.get("Breakout20_status")]),
            })
        print("RUNS_UNCHANGED", db.query(CandidateEvaluationRun).count())
    finally:
        db.close()

    rules = {
        "close > SMA50": "close_gt_SMA50",
        "close > SMA200": "close_gt_SMA200",
        "SMA50 > SMA200": "SMA50_gt_SMA200",
        "close > SMA50 AND SMA50 > SMA200": None,
        "MACD > signal": "MACD_gt_signal",
        "ROC20 > 0": "ROC20_gt_0",
        "Breakout20 POSITIVE": None,
        "close > SMA50 AND ROC20 > 0": None,
        "close > SMA200 AND SMA50 > SMA200": None,
        "close > SMA50 AND MACD > signal": None,
    }

    def passes(row, name):
        if name == "close > SMA50 AND SMA50 > SMA200":
            return row["close_gt_SMA50"] and row["SMA50_gt_SMA200"]
        if name == "Breakout20 POSITIVE":
            return row["Breakout20"] == "POSITIVE"
        if name == "close > SMA50 AND ROC20 > 0":
            return row["close_gt_SMA50"] and row["ROC20_gt_0"]
        if name == "close > SMA200 AND SMA50 > SMA200":
            return row["close_gt_SMA200"] and row["SMA50_gt_SMA200"]
        if name == "close > SMA50 AND MACD > signal":
            return row["close_gt_SMA50"] and row["MACD_gt_signal"]
        return row[rules[name]]

    sim = {}
    for name in rules:
        p = [r["symbol"] for r in rows if passes(r, name)]
        f = [r["symbol"] for r in rows if not passes(r, name)]
        sim[name] = {
            "pass": p,
            "fail": f,
            "selectivity": f"{len(p)}/10",
            "evidence_complete": all(r["complete"] for r in rows),
        }

    out = {"rows": rows, "simulation": sim}
    dest = ROOT / "manual_inputs" / "fundamentals" / "batch_a_phase5_threshold_evidence.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("WROTE", dest)
    for r in rows:
        print(
            r["symbol"], "c", r["close"], "s20", r["SMA20"], "s50", r["SMA50"], "s200", r["SMA200"],
            "c>s50", r["close_gt_SMA50"], "c>s200", r["close_gt_SMA200"], "s50>s200", r["SMA50_gt_SMA200"],
            "RSI", r["RSI14"], "MACD>sig", r["MACD_gt_signal"], "ROC>0", r["ROC20_gt_0"],
            "BO", r["Breakout20"], "ATR%", r["ATR_percent"], "RR", r["RR"],
        )
    for name, s in sim.items():
        print("RULE", name, "pass", s["pass"], "fail", s["fail"], s["selectivity"])


if __name__ == "__main__":
    main()
