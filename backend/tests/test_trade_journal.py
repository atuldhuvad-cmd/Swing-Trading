import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models import StockMaster, CandidateEvaluationRun, RiskRewardResult
from decimal import Decimal
from datetime import datetime, timezone



@pytest.fixture
def setup_trade_data(db_session):
    # Basic stock
    stock = StockMaster(nse_symbol='TRADETEST', company_name='Trade Test')
    db_session.add(stock)
    
    stock2 = StockMaster(nse_symbol='TRADETEST2', company_name='Trade Test 2')
    db_session.add(stock2)
    db_session.commit()
    db_session.refresh(stock)
    db_session.refresh(stock2)

    # Candidate eval
    run = CandidateEvaluationRun(stock_id=stock.stock_id, classification='FINAL_CANDIDATE', config_fingerprint='abc', config_snapshot='{}', evaluation_date=datetime.now(timezone.utc))
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    # RR result
    rr = RiskRewardResult(evaluation_id=run.evaluation_id, entry_reference=100.0, stop_loss=90.0, target=120.0, config_fingerprint='xyz', config_snapshot='{}')
    db_session.add(rr)
    db_session.commit()
    db_session.refresh(rr)
    
    return stock, stock2, run, rr

def test_position_size_calculation(client):
    # Valid calculation
    res = client.post('/api/trades/position-size', json={
        'entry_price': 100.0, 'stop_price': 90.0, 'max_risk_amount': 500.0
    })
    assert res.status_code == 200, res.json()
    data = res.json()
    assert data['status'] == 'CALCULATED'
    assert data['quantity'] == 50
    assert float(data['per_share_risk']) == 10.0
    assert float(data['total_capital']) == 5000.0

    # Max capital cap
    res = client.post('/api/trades/position-size', json={
        'entry_price': 100.0, 'stop_price': 90.0, 'max_risk_amount': 500.0, 'max_capital_allocation': 2000.0
    })
    assert res.json()['quantity'] == 20

    # Invalid prices
    res = client.post('/api/trades/position-size', json={
        'entry_price': 90.0, 'stop_price': 100.0, 'max_risk_amount': 500.0
    })
    assert res.json()['status'] == 'NOT_CALCULATED'

    # Missing inputs should fail validation
    res = client.post('/api/trades/position-size', json={
        'entry_price': 100.0, 'max_risk_amount': 500.0
    })
    assert res.status_code == 422

def test_trade_linkage_validation(client, setup_trade_data):
    stock, stock2, run, rr = setup_trade_data
    
    # Valid
    payload = {
        'stock_id': stock.stock_id,
        'candidate_evaluation_id': run.evaluation_id,
        'risk_reward_result_id': rr.result_id,
        'status': 'PLANNED',
        'side': 'LONG'
    }
    res = client.post('/api/trades/', json=payload)
    assert res.status_code == 200, res.json()

    # Invalid side
    payload['side'] = 'SHORT'
    res = client.post('/api/trades/', json=payload)
    assert res.status_code == 422

    # Cross-stock linkage rejected
    payload['side'] = 'LONG'
    payload['stock_id'] = stock2.stock_id
    res = client.post('/api/trades/', json=payload)
    assert res.status_code == 422
    assert "does not belong" in res.json()['detail']

def test_trade_lifecycle(client, setup_trade_data):
    stock, stock2, run, rr = setup_trade_data
    
    # 1. Create planned trade
    payload = {
        'stock_id': stock.stock_id,
        'candidate_evaluation_id': run.evaluation_id,
        'risk_reward_result_id': rr.result_id,
        'status': 'PLANNED',
        'planned_entry_price': 100.0,
        'planned_stop_price': 90.0,
        'planned_target_price': 120.0,
        'trade_notes': 'Looks good'
    }
    res = client.post('/api/trades/', json=payload)
    assert res.status_code == 200, res.json()
    trade = res.json()
    assert trade['status'] == 'PLANNED'
    assert trade['trade_id'] > 0
    trade_id = trade['trade_id']

    # Invalid OPEN transition (missing provenance)
    res = client.patch(f'/api/trades/{trade_id}', json={
        'status': 'OPEN'
    })
    assert res.status_code == 422
    assert "require quantity > 0" in res.json()['detail']

    # 2. Open trade
    res = client.patch(f'/api/trades/{trade_id}', json={
        'status': 'OPEN',
        'quantity': 50,
        'entry_price': 100.5,
        'entry_date': '2026-08-19T10:00:00Z',
        'entry_price_source': 'Manual observation'
    })
    assert res.status_code == 200, res.json()
    opened = res.json()
    assert opened['status'] == 'OPEN'
    assert opened['quantity'] == 50
    assert float(opened['entry_price']) == 100.5
    assert opened['entry_price_source'] == 'Manual observation'

    # 3. Close trade with profit
    res = client.patch(f'/api/trades/{trade_id}', json={
        'status': 'CLOSED',
        'exit_price': 120.5,
        'exit_date': '2026-08-25T10:00:00Z',
        'exit_price_source': 'Broker app'
    })
    assert res.status_code == 200, res.json()
    closed = res.json()
    assert closed['status'] == 'CLOSED'
    # Gross PnL: (120.5 - 100.5) * 50 = 1000.0
    assert float(closed['gross_pnl']) == 1000.0
    assert closed['net_pnl'] is None

    # Invalid transition from CLOSED
    res = client.patch(f'/api/trades/{trade_id}', json={
        'status': 'OPEN'
    })
    assert res.status_code == 422
    assert "Invalid transition" in res.json()['detail']

    # Invalid transition from CLOSED to CANCELLED
    res = client.patch(f'/api/trades/{trade_id}', json={
        'status': 'CANCELLED'
    })
    assert res.status_code == 422
    assert "Invalid transition" in res.json()['detail']

def test_trade_cancel_lifecycle(client, setup_trade_data):
    """PLANNED → CANCELLED lifecycle"""
    stock, _, _, _ = setup_trade_data
    res = client.post('/api/trades/', json={'stock_id': stock.stock_id, 'status': 'PLANNED',
                                            'planned_entry_price': 100.0})
    assert res.status_code == 200, res.json()
    trade_id = res.json()['trade_id']

    # PLANNED → CANCELLED
    res = client.patch(f'/api/trades/{trade_id}', json={'status': 'CANCELLED'})
    assert res.status_code == 200, res.json()
    assert res.json()['status'] == 'CANCELLED'

    # CANCELLED → OPEN must be rejected
    res = client.patch(f'/api/trades/{trade_id}', json={
        'status': 'OPEN',
        'quantity': 10,
        'entry_price': 100.0,
        'entry_date': '2026-08-19T10:00:00Z',
        'entry_price_source': 'Broker app'
    })
    assert res.status_code == 422
    assert "Invalid transition" in res.json()['detail']

def test_data_persistence(client, db_session, setup_trade_data):
    stock, _, _, _ = setup_trade_data
    res = client.post('/api/trades/', json={'stock_id': stock.stock_id, 'status': 'PLANNED'})
    assert res.status_code == 200, res.json()
    trade_id = res.json()['trade_id']
    res = client.get(f'/api/trades/{trade_id}')
    assert res.status_code == 200, res.json()
    assert res.json()['status'] == 'PLANNED'

def test_open_requires_entry_price_source(client, setup_trade_data):
    """entry_price_source is required when opening"""
    stock, _, _, _ = setup_trade_data
    res = client.post('/api/trades/', json={'stock_id': stock.stock_id, 'status': 'PLANNED'})
    trade_id = res.json()['trade_id']

    # Missing entry_price_source
    res = client.patch(f'/api/trades/{trade_id}', json={
        'status': 'OPEN',
        'quantity': 10,
        'entry_price': 100.0,
        'entry_date': '2026-08-19T10:00:00Z',
        # no entry_price_source
    })
    assert res.status_code == 422
    assert "entry_price_source" in res.json()['detail']

def test_close_requires_exit_price_source(client, setup_trade_data):
    """exit_price_source is required when closing"""
    stock, _, _, _ = setup_trade_data
    res = client.post('/api/trades/', json={'stock_id': stock.stock_id, 'status': 'PLANNED'})
    trade_id = res.json()['trade_id']
    # Open it first
    client.patch(f'/api/trades/{trade_id}', json={
        'status': 'OPEN', 'quantity': 10, 'entry_price': 100.0,
        'entry_date': '2026-08-19T10:00:00Z', 'entry_price_source': 'Manual'
    })
    # Try closing without exit_price_source
    res = client.patch(f'/api/trades/{trade_id}', json={
        'status': 'CLOSED',
        'exit_price': 110.0,
        'exit_date': '2026-08-20T10:00:00Z',
        # no exit_price_source
    })
    assert res.status_code == 422
    assert "exit_price_source" in res.json()['detail']

def test_entry_source_persists(client, setup_trade_data):
    """After opening, entry_price_source is retrievable via GET"""
    stock, _, _, _ = setup_trade_data
    res = client.post('/api/trades/', json={'stock_id': stock.stock_id, 'status': 'PLANNED'})
    trade_id = res.json()['trade_id']
    client.patch(f'/api/trades/{trade_id}', json={
        'status': 'OPEN', 'quantity': 5, 'entry_price': 200.0,
        'entry_date': '2026-08-19T10:00:00Z', 'entry_price_source': 'NSE website'
    })
    fetched = client.get(f'/api/trades/{trade_id}').json()
    assert fetched['entry_price_source'] == 'NSE website'
    assert fetched['status'] == 'OPEN'

def test_exit_source_persists(client, setup_trade_data):
    """After closing, exit_price_source is retrievable via GET"""
    stock, _, _, _ = setup_trade_data
    res = client.post('/api/trades/', json={'stock_id': stock.stock_id, 'status': 'PLANNED'})
    trade_id = res.json()['trade_id']
    client.patch(f'/api/trades/{trade_id}', json={
        'status': 'OPEN', 'quantity': 5, 'entry_price': 200.0,
        'entry_date': '2026-08-19T10:00:00Z', 'entry_price_source': 'Broker app'
    })
    client.patch(f'/api/trades/{trade_id}', json={
        'status': 'CLOSED', 'exit_price': 220.0,
        'exit_date': '2026-08-20T10:00:00Z', 'exit_price_source': 'NSE website'
    })
    fetched = client.get(f'/api/trades/{trade_id}').json()
    assert fetched['exit_price_source'] == 'NSE website'
    assert fetched['status'] == 'CLOSED'
