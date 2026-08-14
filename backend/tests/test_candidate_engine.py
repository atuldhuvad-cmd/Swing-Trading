import pytest
from datetime import datetime
from decimal import Decimal
from app.models import StockMaster
from app.services.candidate_service import CandidateService

def test_missing_config(db_session):
    stock = StockMaster(nse_symbol='TEST1', company_name='Test 1')
    db_session.add(stock)
    db_session.commit()
    
    run = CandidateService.evaluate_candidate(db_session, stock.stock_id, {}, {}, {})
    assert run.classification == 'RULE_CONFIGURATION_REQUIRED'
    assert run.config_fingerprint == 'EMPTY'

def test_final_candidate(db_session):
    stock = StockMaster(nse_symbol='TEST2', company_name='Test 2')
    db_session.add(stock)
    db_session.commit()
    
    config = {
        'criteria': [
            {'id': 'SMA50', 'type': 'TECHNICAL', 'operator': '>=', 'threshold': 100, 'mandatory': True},
            {'id': 'revenue', 'type': 'FUNDAMENTAL', 'operator': '>', 'threshold': 0, 'mandatory': True}
        ]
    }
    tech = {'SMA50': 150}
    fund = {'revenue': {'value': 1000, 'status': 'KNOWN'}}
    
    run = CandidateService.evaluate_candidate(db_session, stock.stock_id, config, tech, fund)
    assert run.classification == 'FINAL_CANDIDATE'

def test_watch_candidate(db_session):
    stock = StockMaster(nse_symbol='TEST3', company_name='Test 3')
    db_session.add(stock)
    db_session.commit()
    
    config = {
        'criteria': [
            {'id': 'SMA50', 'type': 'TECHNICAL', 'operator': '>=', 'threshold': 100, 'mandatory': True},
            {'id': 'revenue', 'type': 'FUNDAMENTAL', 'operator': '>', 'threshold': 1000, 'mandatory': False}
        ]
    }
    tech = {'SMA50': 150}
    fund = {'revenue': {'value': 500, 'status': 'KNOWN'}}
    
    run = CandidateService.evaluate_candidate(db_session, stock.stock_id, config, tech, fund)
    assert run.classification == 'WATCH'

def test_rejected_candidate(db_session):
    stock = StockMaster(nse_symbol='TEST4', company_name='Test 4')
    db_session.add(stock)
    db_session.commit()
    
    config = {
        'criteria': [
            {'id': 'SMA50', 'type': 'TECHNICAL', 'operator': '>=', 'threshold': 100, 'mandatory': True},
        ]
    }
    tech = {'SMA50': 50}
    fund = {}
    
    run = CandidateService.evaluate_candidate(db_session, stock.stock_id, config, tech, fund)
    assert run.classification == 'REJECTED'

def test_insufficient_data(db_session):
    stock = StockMaster(nse_symbol='TEST5', company_name='Test 5')
    db_session.add(stock)
    db_session.commit()
    
    config = {
        'criteria': [
            {'id': 'SMA50', 'type': 'TECHNICAL', 'operator': '>=', 'threshold': 100, 'mandatory': True},
        ]
    }
    tech = {'SMA50': None}
    fund = {}
    
    run = CandidateService.evaluate_candidate(db_session, stock.stock_id, config, tech, fund)
    assert run.classification == 'INSUFFICIENT_DATA'

def test_insufficient_data_nan(db_session):
    stock = StockMaster(nse_symbol='TEST6', company_name='Test 6')
    db_session.add(stock)
    db_session.commit()
    
    config = {
        'criteria': [
            {'id': 'SMA50', 'type': 'TECHNICAL', 'operator': '>=', 'threshold': 100, 'mandatory': True},
        ]
    }
    tech = {'SMA50': float('nan')}
    fund = {}
    
    run = CandidateService.evaluate_candidate(db_session, stock.stock_id, config, tech, fund)
    assert run.classification == 'INSUFFICIENT_DATA'

def test_not_applicable(db_session):
    stock = StockMaster(nse_symbol='TEST7', company_name='Test 7')
    db_session.add(stock)
    db_session.commit()
    
    config = {
        'criteria': [
            {'id': 'inventory', 'type': 'FUNDAMENTAL', 'operator': '>', 'threshold': 0, 'mandatory': True}
        ]
    }
    tech = {}
    fund = {'inventory': {'value': None, 'status': 'NOT_APPLICABLE'}}
    
    run = CandidateService.evaluate_candidate(db_session, stock.stock_id, config, tech, fund)
    assert run.classification == 'REJECTED'

def test_adversarial_dict_ordering(db_session):
    stock = StockMaster(nse_symbol='TEST8', company_name='Test 8')
    db_session.add(stock)
    db_session.commit()
    
    c1 = {'criteria': [{'id': 'A', 'operator': '>', 'threshold': 10, 'mandatory': True}]}
    c2 = {'criteria': [{'mandatory': True, 'threshold': 10, 'operator': '>', 'id': 'A'}]}
    
    fp1 = CandidateService.get_config_fingerprint(c1)
    fp2 = CandidateService.get_config_fingerprint(c2)
    assert fp1 == fp2
