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


def _phase5_insufficient_run(db_session, stock_id):
    """Mirror a short-history stock: only RSI14/ATR14 known, no fundamentals."""
    from app.services.candidate_config import PHASE5_TREND_SCREEN_V1
    tech = {"SMA20": None, "SMA50": None, "SMA200": None, "ATR14": Decimal("61.29"),
            "latest_close": Decimal("2105.0"), "sessions": 18}
    return CandidateService.evaluate_candidate(db_session, stock_id, PHASE5_TREND_SCREEN_V1, tech, {})


def test_criterion_order_identical_across_list_and_detail(client, db_session):
    from app.services.candidate_config import PHASE5_TREND_SCREEN_V1
    stock = db_session.query(StockMaster).filter_by(nse_symbol="RELIANCE").one()
    run = _phase5_insufficient_run(db_session, stock.stock_id)
    db_session.commit()
    assert run.classification == "INSUFFICIENT_DATA"

    config_order = [c["id"] for c in PHASE5_TREND_SCREEN_V1["criteria"]]
    assert config_order != sorted(config_order)  # alphabetical order would change the rule sequence

    detail = client.get(f"/api/evidence/stocks/{stock.stock_id}").json()
    listed = next(i for i in client.get("/api/evidence/candidates").json()["items"]
                  if i["evaluation_id"] == run.evaluation_id)
    assert detail["candidate"]["evaluation_id"] == run.evaluation_id

    def view(rows):
        return [(r["criterion"], r["result"], r["reason"], r["evidence_value"], r["operator"], r["threshold"])
                for r in rows]

    assert [r["criterion"] for r in detail["criteria"]] == config_order
    assert view(listed["criteria"]) == view(detail["criteria"])
    assert listed["decisive_reason"] == detail["candidate"]["decisive_reason"]
    unknown = [c for c in config_order if next(r for r in detail["criteria"] if r["criterion"] == c)["result"] == "UNKNOWN"]
    assert detail["candidate"]["decisive_reason"] == "Mandatory evidence unavailable: " + ", ".join(unknown)
    # UNKNOWN is never reported as PASS in either endpoint
    for rows in (listed["criteria"], detail["criteria"]):
        assert all(r["evidence_value"] is not None for r in rows if r["result"] == "PASS")


def test_historical_evaluation_keeps_its_own_config_order(client, db_session):
    from app.services.candidate_config import LEGACY_BATCH_A_POST_IMPORT_CONFIG, PHASE5_TREND_SCREEN_V1
    from app.services.evidence_service import EvidenceService
    stock = db_session.query(StockMaster).filter_by(nse_symbol="RELIANCE").one()
    legacy = CandidateService.evaluate_candidate(
        db_session, stock.stock_id, LEGACY_BATCH_A_POST_IMPORT_CONFIG, {"SMA20": Decimal("1")}, {})
    latest = _phase5_insufficient_run(db_session, stock.stock_id)
    db_session.commit()

    grouped = EvidenceService.criteria_by_evaluation(db_session, [latest.evaluation_id, legacy.evaluation_id])
    legacy_order = [c["id"] for c in LEGACY_BATCH_A_POST_IMPORT_CONFIG["criteria"]]
    assert legacy_order != sorted(legacy_order)
    assert [r.criterion_identifier for r in grouped[legacy.evaluation_id]] == legacy_order
    assert [r.criterion_identifier for r in grouped[latest.evaluation_id]] == [c["id"] for c in PHASE5_TREND_SCREEN_V1["criteria"]]

    # Endpoints expose the latest evaluation; its order is unaffected by the older run.
    detail = client.get(f"/api/evidence/stocks/{stock.stock_id}").json()
    listed = next(i for i in client.get("/api/evidence/candidates").json()["items"] if i["stock_id"] == stock.stock_id)
    assert detail["candidate"]["evaluation_id"] == listed["evaluation_id"] == latest.evaluation_id
    assert [r["criterion"] for r in detail["criteria"]] == [r["criterion"] for r in listed["criteria"]]
