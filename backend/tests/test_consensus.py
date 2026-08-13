import pytest
from datetime import datetime, timedelta
from app.models import (
    StockMaster, BrokerMaster, BrokerRecommendation, SourceReference,
    RecommendationSource, StockPrice, SourceTypeMaster
)
from app.services.consensus_service import ConsensusService

def setup_source_type(db):
    st = db.query(SourceTypeMaster).filter(SourceTypeMaster.type_name == "WEBSITE").first()
    if not st:
        st = SourceTypeMaster(type_name="WEBSITE", description="Web article")
        db.add(st)
        db.commit()
        db.refresh(st)
    return st

def test_unique_broker_count_and_latest_selection(db_session):
    st = setup_source_type(db_session)
    
    # Create Stock
    stock = StockMaster(nse_symbol="RELIANCE_TEST", company_name="Reliance Industries Test")
    db_session.add(stock)
    
    # Create Brokers
    broker1 = BrokerMaster(canonical_name="ICICI Sec Test 1", normalized_name="icici_sec_test_1", display_name="ICICI Sec Test 1")
    broker2 = BrokerMaster(canonical_name="HDFC Sec Test 1", normalized_name="hdfc_sec_test_1", display_name="HDFC Sec Test 1")
    db_session.add_all([broker1, broker2])
    db_session.commit()

    now = datetime.utcnow()
    
    # Broker 1 older rec (10 days ago)
    rec1_old = BrokerRecommendation(
        stock_id=stock.stock_id,
        broker_id=broker1.broker_id,
        recommendation_date=now - timedelta(days=10),
        original_rating="BUY",
        normalized_rating="BUY",
        target_price=2500.0,
        lifecycle_status="SUPERSEDED"
    )
    # Broker 1 newer rec (2 days ago) - CURRENT
    rec1_new = BrokerRecommendation(
        stock_id=stock.stock_id,
        broker_id=broker1.broker_id,
        recommendation_date=now - timedelta(days=2),
        original_rating="BUY",
        normalized_rating="BUY",
        target_price=2700.0,
        lifecycle_status="CURRENT"
    )
    # Broker 2 rec (5 days ago) - CURRENT
    rec2 = BrokerRecommendation(
        stock_id=stock.stock_id,
        broker_id=broker2.broker_id,
        recommendation_date=now - timedelta(days=5),
        original_rating="HOLD",
        normalized_rating="HOLD",
        target_price=2400.0,
        lifecycle_status="CURRENT"
    )
    db_session.add_all([rec1_old, rec1_new, rec2])
    db_session.commit()

    consensus = ConsensusService.calculate_stock_consensus(db_session, stock.stock_id)
    assert consensus is not None
    assert consensus.metrics.unique_broker_count == 2
    # Check that Broker 1's target is 2700 (latest)
    b1_contrib = next(c for c in consensus.contributors if c.broker_id == broker1.broker_id)
    assert b1_contrib.target_price == 2700.0

def test_multiple_sources_non_inflation(db_session):
    st = setup_source_type(db_session)
    
    stock = StockMaster(nse_symbol="TCS_TEST", company_name="Tata Consultancy Services Test")
    broker = BrokerMaster(canonical_name="Motilal Oswal Test", normalized_name="motilal_oswal_test", display_name="Motilal Oswal Test")
    db_session.add_all([stock, broker])
    db_session.commit()

    rec = BrokerRecommendation(
        stock_id=stock.stock_id,
        broker_id=broker.broker_id,
        recommendation_date=datetime.utcnow(),
        original_rating="BUY",
        normalized_rating="BUY",
        target_price=4200.0,
        lifecycle_status="CURRENT"
    )
    db_session.add(rec)
    db_session.commit()

    # Add 3 distinct evidence sources for this 1 recommendation
    src1 = SourceReference(source_type_id=st.source_type_id, publication_name="Moneycontrol", url="http://mc.com/1", verification_status="VERIFIED_PRIMARY")
    src2 = SourceReference(source_type_id=st.source_type_id, publication_name="Economic Times", url="http://et.com/1", verification_status="VERIFIED_SECONDARY")
    src3 = SourceReference(source_type_id=st.source_type_id, publication_name="Broker Website", url="http://motilal.com/1", verification_status="VERIFIED_PRIMARY")
    db_session.add_all([src1, src2, src3])
    db_session.commit()

    db_session.add_all([
        RecommendationSource(recommendation_id=rec.recommendation_id, source_reference_id=src1.source_reference_id),
        RecommendationSource(recommendation_id=rec.recommendation_id, source_reference_id=src2.source_reference_id),
        RecommendationSource(recommendation_id=rec.recommendation_id, source_reference_id=src3.source_reference_id)
    ])
    db_session.commit()

    consensus = ConsensusService.calculate_stock_consensus(db_session, stock.stock_id)
    assert consensus is not None
    # MUST remain 1 broker, 1 recommendation, multiple sources
    assert consensus.metrics.unique_broker_count == 1
    assert len(consensus.contributors) == 1
    assert len(consensus.contributors[0].sources) == 3

def test_median_target_and_upside_calculations(db_session):
    stock = StockMaster(nse_symbol="INFY_TEST", company_name="Infosys Ltd Test")
    db_session.add(stock)
    db_session.commit()

    # Set CMP = 1000
    sp = StockPrice(stock_id=stock.stock_id, last_price=1000.0)
    db_session.add(sp)

    brokers = [
        BrokerMaster(canonical_name=f"Broker_{i}_Test", normalized_name=f"broker_{i}_test", display_name=f"Broker {i} Test")
        for i in range(1, 5)
    ]
    db_session.add_all(brokers)
    db_session.commit()

    targets = [1100.0, 1300.0, 1500.0, 1700.0]
    for b, t in zip(brokers, targets):
        rec = BrokerRecommendation(
            stock_id=stock.stock_id,
            broker_id=b.broker_id,
            recommendation_date=datetime.utcnow(),
            original_rating="BUY",
            normalized_rating="BUY",
            target_price=t,
            lifecycle_status="CURRENT"
        )
        db_session.add(rec)
    db_session.commit()

    consensus = ConsensusService.calculate_stock_consensus(db_session, stock.stock_id)
    m = consensus.metrics
    assert m.unique_broker_count == 4
    assert m.total_target_count == 4
    assert m.target_coverage_pct == 100.0
    assert m.min_target == 1100.0
    assert m.max_target == 1700.0
    assert m.avg_target == 1400.0
    # Median of [1100, 1300, 1500, 1700] is (1300 + 1500) / 2 = 1400.0
    assert m.median_target == 1400.0
    # Upside calculation: (1400 - 1000)/1000 * 100 = 40.0%
    assert m.avg_target_upside_pct == 40.0
    assert m.median_target_upside_pct == 40.0

def test_lifecycle_vs_freshness_independence(db_session):
    stock = StockMaster(nse_symbol="SBIN_TEST", company_name="State Bank of India Test")
    broker = BrokerMaster(canonical_name="Axis Capital Test", normalized_name="axis_capital_test", display_name="Axis Capital Test")
    db_session.add_all([stock, broker])
    db_session.commit()

    now = datetime.utcnow()
    old_date = now - timedelta(days=75) # 75 days old (> 60 days)
    
    rec = BrokerRecommendation(
        stock_id=stock.stock_id,
        broker_id=broker.broker_id,
        recommendation_date=old_date,
        original_rating="BUY",
        normalized_rating="BUY",
        target_price=800.0,
        lifecycle_status="CURRENT"
    )
    db_session.add(rec)
    db_session.commit()

    consensus = ConsensusService.calculate_stock_consensus(db_session, stock.stock_id)
    contrib = consensus.contributors[0]
    assert contrib.lifecycle_status == "CURRENT"
    assert contrib.age_days >= 75
    assert contrib.freshness_category == "AGED"
    assert consensus.metrics.freshness_summary == "AGED"

def test_candidate_endpoints(client, db_session):
    stock = StockMaster(nse_symbol="LT_TEST", company_name="Larsen & Toubro Ltd Test")
    broker = BrokerMaster(canonical_name="BOB Capital Test", normalized_name="bob_capital_test", display_name="BOB Capital Test")
    db_session.add_all([stock, broker])
    db_session.commit()

    sp = StockPrice(stock_id=stock.stock_id, last_price=3000.0)
    db_session.add(sp)

    rec = BrokerRecommendation(
        stock_id=stock.stock_id,
        broker_id=broker.broker_id,
        recommendation_date=datetime.utcnow(),
        original_rating="BUY",
        normalized_rating="BUY",
        target_price=3600.0,
        lifecycle_status="CURRENT"
    )
    db_session.add(rec)
    db_session.commit()

    # Test Candidate Universe Endpoint
    response = client.get("/api/consensus/candidates?min_brokers=1")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    item = next(i for i in data["items"] if i["nse_symbol"] == "LT_TEST")
    assert item["unique_broker_count"] == 1
    assert item["bullish_percentage"] == 100.0
    assert item["avg_target_upside_pct"] == 20.0 # (3600-3000)/3000 * 100

    # Test Stock Detail Endpoint
    response_detail = client.get(f"/api/consensus/stocks/{stock.stock_id}")
    assert response_detail.status_code == 200
    detail = response_detail.json()
    assert detail["nse_symbol"] == "LT_TEST"
    assert detail["metrics"]["unique_broker_count"] == 1
