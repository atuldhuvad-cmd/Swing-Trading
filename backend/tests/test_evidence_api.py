from decimal import Decimal
from app.models import StockMaster, DailyOhlcv, CandidateEvaluationRun
from app.services.candidate_service import CandidateService
from app.services.risk_reward_service import RiskRewardService


def test_evidence_stock_not_found(client):
    res = client.get("/api/evidence/stocks/999999")
    assert res.status_code == 404


def test_evidence_missing_and_ordering(client, db_session):
    stock = db_session.query(StockMaster).filter_by(nse_symbol="RELIANCE").one()
    res = client.get(f"/api/evidence/stocks/{stock.stock_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["candidate"]["classification"] is None
    assert body["risk_reward"] is None
    assert body["technical"]["sessions"] == 0
    assert body["fundamentals"] == []

    market = client.get("/api/evidence/market-data")
    assert market.status_code == 200
    symbols = [i["nse_symbol"] for i in market.json()["items"]]
    assert symbols == sorted(symbols)

    listed = client.get("/api/evidence/candidates")
    assert listed.status_code == 200
    assert listed.json()["items"] == []


def test_evidence_decimal_and_criteria(client, db_session):
    stock = db_session.query(StockMaster).filter_by(nse_symbol="RELIANCE").one()
    from datetime import datetime, timedelta
    for i in range(21):
        db_session.add(DailyOhlcv(
            stock_id=stock.stock_id,
            trading_date=datetime(2026, 1, 1) + timedelta(days=i),
            series="EQ",
            open=100,
            high=101,
            low=99,
            close=100 + i,
            volume=1000,
            source_name="TEST",
        ))
    db_session.commit()
    config = {"criteria": [{"id": "SMA20", "type": "TECHNICAL", "operator": ">=", "threshold": 100, "mandatory": True}]}
    tech = {"SMA20": Decimal("110.5")}
    run = CandidateService.evaluate_candidate(db_session, stock.stock_id, config, tech, {})
    RiskRewardService.calculate_risk_reward(
        db_session, run.evaluation_id, {"atr_multiplier": 1.5, "buffer_percent": 0.01},
        {"ATR14": 2, "Support20": 90, "Resistance20": 130}, 110,
    )
    db_session.commit()

    body = client.get(f"/api/evidence/stocks/{stock.stock_id}").json()
    assert body["candidate"]["classification"] == "FINAL_CANDIDATE"
    assert body["criteria"][0]["criterion"] == "SMA20"
    assert body["criteria"][0]["result"] == "PASS"
    assert isinstance(body["risk_reward"]["rr_ratio"], str)
    assert body["technical"]["indicators"]["SMA20"] is not None

    items = client.get("/api/evidence/candidates").json()["items"]
    assert items[0]["nse_symbol"] == "RELIANCE"
    assert items[0]["status"] == "FINAL_CANDIDATE"
    assert items[0]["evaluation_id"] is not None
    assert items[0]["classification_meaning"]


def test_evidence_consensus(client, db_session):
    # Test stock with no consensus
    stock = db_session.query(StockMaster).filter_by(nse_symbol="RELIANCE").one()
    body = client.get(f"/api/evidence/stocks/{stock.stock_id}").json()
    assert body["consensus"]["status"] == "NO_CONSENSUS"
    assert "metrics" not in body["consensus"]
    
    # Add consensus for HINDALCO
    hindalco = StockMaster(nse_symbol="HINDALCO", company_name="Hindalco Ind")
    db_session.add(hindalco)
    db_session.flush()
    from app.models import BrokerMaster, BrokerRecommendation
    from datetime import datetime
    broker = BrokerMaster(canonical_name="TEST_BROKER", display_name="Test Broker", normalized_name="TEST_BROKER")
    db_session.add(broker)
    db_session.flush()
    db_session.add(BrokerRecommendation(
        stock_id=hindalco.stock_id,
        broker_id=broker.broker_id,
        recommendation_date=datetime(2026, 1, 1),
        original_rating="BUY",
        normalized_rating="BUY",
        target_price=500.0,
        lifecycle_status="CURRENT"
    ))
    db_session.commit()
    
    body = client.get(f"/api/evidence/stocks/{hindalco.stock_id}").json()
    assert body["consensus"]["status"] == "CONSENSUS_AVAILABLE"
    assert body["consensus"]["metrics"]["unique_broker_count"] == 1
    assert body["consensus"]["metrics"]["avg_target"] == 500.0
