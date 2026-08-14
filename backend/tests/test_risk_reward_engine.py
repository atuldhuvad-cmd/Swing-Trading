import pytest
from datetime import datetime
from decimal import Decimal
from app.models import StockMaster, CandidateEvaluationRun, RiskRewardResult
from app.services.risk_reward_service import RiskRewardService

def test_risk_reward_atr(db_session):
    stock = StockMaster(nse_symbol='RR1', company_name='RR1 Co')
    db_session.add(stock)
    db_session.commit()
    
    run = CandidateEvaluationRun(stock_id=stock.stock_id, classification='FINAL_CANDIDATE', config_fingerprint='x', config_snapshot='x')
    db_session.add(run)
    db_session.commit()
    
    config = {'atr_multiplier': 2.0, 'buffer_percent': 0.02}
    tech = {'ATR14': 5.0, 'resistance': 120.0}
    current_price = 100.0
    
    res = RiskRewardService.calculate_risk_reward(db_session, run.evaluation_id, config, tech, current_price)
    
    assert res.stop_loss == Decimal('90.0') # 100 - (5.0 * 2)
    assert res.target == Decimal('117.6') # 120 * (1 - 0.02)
    assert res.risk_per_share == Decimal('10.0') # 100 - 90
    assert res.reward_per_share == Decimal('17.6') # 117.6 - 100
    assert round(res.risk_reward_ratio, 2) == Decimal('1.76')

def test_risk_reward_support(db_session):
    stock = StockMaster(nse_symbol='RR2', company_name='RR2 Co')
    db_session.add(stock)
    db_session.commit()
    
    run = CandidateEvaluationRun(stock_id=stock.stock_id, classification='FINAL_CANDIDATE', config_fingerprint='x', config_snapshot='x')
    db_session.add(run)
    db_session.commit()
    
    config = {'buffer_percent': 0.01}
    tech = {'support': 90.0, 'resistance': 110.0}
    current_price = 100.0
    
    res = RiskRewardService.calculate_risk_reward(db_session, run.evaluation_id, config, tech, current_price)
    
    assert res.stop_loss == Decimal('89.1') # 90 * 0.99
    assert res.target == Decimal('108.9') # 110 * 0.99
    assert res.risk_per_share == Decimal('10.9') # 100 - 89.1
    assert res.reward_per_share == Decimal('8.9') # 108.9 - 100

def test_invalid_values(db_session):
    stock = StockMaster(nse_symbol='RR3', company_name='RR3 Co')
    db_session.add(stock)
    db_session.commit()
    
    run = CandidateEvaluationRun(stock_id=stock.stock_id, classification='FINAL_CANDIDATE', config_fingerprint='x', config_snapshot='x')
    db_session.add(run)
    db_session.commit()
    
    config = {}
    tech = {'ATR14': float('inf'), 'resistance': 90.0} # Resistance below entry
    current_price = 100.0
    
    res = RiskRewardService.calculate_risk_reward(db_session, run.evaluation_id, config, tech, current_price)
    
    assert res.stop_loss is not None
    assert res.target is None
    assert res.reward_per_share is None
    assert res.risk_reward_ratio is None
