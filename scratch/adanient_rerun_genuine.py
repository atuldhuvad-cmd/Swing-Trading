"""Re-run genuine ADANIENT evaluation so latest evidence is Batch A, preserving prior runs."""
import sys
from pathlib import Path
ROOT = Path(r"D:\Swing Trading")
sys.path.insert(0, str(ROOT / "backend"))
from app.database import SessionLocal
from app.models import StockMaster, DailyOhlcv, CandidateEvaluationRun
from app.services.corporate_action_service import CorporateActionService
from app.services.technical_service import TechnicalService
from app.services.candidate_service import CandidateService
from app.services.fundamental_service import FundamentalService
from app.services.risk_reward_service import RiskRewardService
from decimal import Decimal

CONFIG = {
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

db = SessionLocal()
try:
    stock = db.query(StockMaster).filter_by(nse_symbol="ADANIENT").one()
    before_ids = [r.evaluation_id for r in db.query(CandidateEvaluationRun).filter_by(stock_id=stock.stock_id).all()]
    raw = db.query(DailyOhlcv).filter_by(stock_id=stock.stock_id, series="EQ").order_by(DailyOhlcv.trading_date.asc()).all()
    originals = [(r.open, r.high, r.low, r.close, r.volume) for r in raw]
    adj = CorporateActionService.apply_adjustments(db, stock.stock_id, raw)
    assert originals == [(r.open, r.high, r.low, r.close, r.volume) for r in raw]
    tech = TechnicalService.calculate_technical_evidence(adj)
    tech_for_eval = {k: tech.get(k) for k in ["SMA20","SMA50","SMA200","RSI14","MACD","MACD_signal","MACD_hist","ATR14","ATR_percent","ROC20","Liquidity20"]}
    fund = {}
    snap = FundamentalService.get_latest_snapshot(db, stock.stock_id)
    run = CandidateService.evaluate_candidate(db, stock.stock_id, CONFIG, tech_for_eval, fund, f"prod_ohlcv_ADANIENT_{len(raw)}", snap.snapshot_id if snap else None)
    close = tech.get("latest_close")
    atr, sup, res = tech.get("ATR14"), tech.get("Support20"), tech.get("Resistance20")
    if close is not None and atr is not None and res is not None:
        entry = Decimal(str(close))
        stop = entry - Decimal(str(atr)) * Decimal("1.5")
        target = Decimal(str(res)) * Decimal("0.99")
        if stop > 0 and stop < entry and target > entry:
            RiskRewardService.calculate_risk_reward(db, run.evaluation_id, {"atr_multiplier": 1.5, "buffer_percent": 0.01}, tech, float(close))
    db.commit()
    after = db.query(CandidateEvaluationRun).filter_by(stock_id=stock.stock_id).all()
    still = all(db.get(CandidateEvaluationRun, i) is not None for i in before_ids)
    print("before", before_ids, "new", run.evaluation_id, "class", run.classification, "preserved", still, "count", len(after))
finally:
    db.close()
