import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.database import SessionLocal, engine
from app.schema_readiness import guard_script_write  # noqa: E402  (refuses a stale schema before any write)

from app.models import StockMaster
from app.services.technical_service import TechnicalService
from app.services.candidate_service import CandidateService
from app.services.risk_reward_service import RiskRewardService

def run_proof():
    guard_script_write(SessionLocal)
    db = SessionLocal()
    try:
        # Get specific stock with OHLCV data
        stock = db.query(StockMaster).filter(StockMaster.nse_symbol == 'CARYSIL').first()
        if not stock:
            print("No stock found.")
            return

        print(f"Running Proof for {stock.nse_symbol}")
        
        from app.models import DailyOhlcv
        ohlcv_records = db.query(DailyOhlcv).filter(DailyOhlcv.stock_id == stock.stock_id).order_by(DailyOhlcv.trading_date.desc()).limit(200).all()
        ohlcv_records.reverse()
        
        adjusted_ohlcv = []
        for rec in ohlcv_records:
            adjusted_ohlcv.append({
                'trading_date': rec.trading_date,
                'open': float(rec.open),
                'high': float(rec.high),
                'low': float(rec.low),
                'close': float(rec.close),
                'volume': int(rec.volume) if rec.volume else 0
            })
            
        tech_evidence = TechnicalService.calculate_technical_evidence(adjusted_ohlcv)
        tech_ref = f"run_{stock.nse_symbol}_{len(adjusted_ohlcv)}_days"
        print(f"Tech Evidence keys: {list(tech_evidence.keys())[:5]}")
        
        # 2. Fund Analysis
        fund_evidence = {}
        print("Fund Evidence: {}")
        
        # 3. Candidate
        config_candidate = {
            'criteria': [
                {'id': 'SMA50', 'type': 'TECHNICAL', 'operator': '>=', 'threshold': 100, 'mandatory': False},
            ]
        }
        run = CandidateService.evaluate_candidate(
            db, stock.stock_id, config_candidate, tech_evidence, fund_evidence, tech_ref
        )
        print(f"Candidate Classification: {run.classification}")
        
        # 4. RR
        config_rr = {'atr_multiplier': 1.5, 'buffer_percent': 0.01}
        # Simulate a current price since we don't have real time
        current_price = tech_evidence.get('SMA50', 100.0)
        
        if current_price is None:
            current_price = 100.0
            
        rr_res = RiskRewardService.calculate_risk_reward(db, run.evaluation_id, config_rr, tech_evidence, float(current_price))
        print(f"Risk Reward Ratio: {rr_res.risk_reward_ratio}")
        
        print("End to End Proof Successful")
    finally:
        db.rollback()
        db.close()

if __name__ == '__main__':
    run_proof()
