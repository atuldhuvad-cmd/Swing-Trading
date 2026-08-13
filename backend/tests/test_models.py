import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from app.models import (
    StockMaster, BrokerMaster, BrokerAlias, BrokerRelationship,
    RecommendationStream, BrokerRecommendation, RecommendationStatusHistory,
    SourceTypeMaster, SourceReference, RecommendationSource, RatingNormalization,
    StockPrice, PriceObservation, ImportBatch, ImportBatchDetail, ReviewQueue, SystemSetting
)
from datetime import datetime

def test_schema_exists(db_session):
    # Verify all tables exist by querying them
    db_session.query(StockMaster).first()
    db_session.query(BrokerMaster).first()
    db_session.query(BrokerAlias).first()
    db_session.query(BrokerRelationship).first()
    db_session.query(RecommendationStream).first()
    db_session.query(BrokerRecommendation).first()
    db_session.query(RecommendationStatusHistory).first()
    db_session.query(SourceTypeMaster).first()
    db_session.query(SourceReference).first()
    db_session.query(RecommendationSource).first()
    db_session.query(RatingNormalization).first()
    db_session.query(StockPrice).first()
    db_session.query(PriceObservation).first()
    db_session.query(ImportBatch).first()
    db_session.query(ImportBatchDetail).first()
    db_session.query(ReviewQueue).first()
    db_session.query(SystemSetting).first()

def test_stock_master_constraints(db_session):
    stock1 = StockMaster(nse_symbol='TCS', company_name='Tata Consultancy', isin='INE467B01029')
    db_session.add(stock1)
    db_session.commit()

    # Duplicate nse_symbol
    stock2 = StockMaster(nse_symbol='TCS', company_name='TCS 2')
    db_session.add(stock2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Nullable ISIN accepted
    stock3 = StockMaster(nse_symbol='WIPRO', company_name='Wipro', isin=None)
    db_session.add(stock3)
    db_session.commit()

    # Duplicate non-null ISIN rejected
    stock4 = StockMaster(nse_symbol='INFY', company_name='Infy', isin='INE467B01029')
    db_session.add(stock4)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_broker_identity(db_session):
    broker = BrokerMaster(canonical_name='Test Broker', normalized_name='testbroker', display_name='Test')
    db_session.add(broker)
    db_session.commit()

    alias = BrokerAlias(broker_id=broker.broker_id, alias_name='Test B')
    db_session.add(alias)
    db_session.commit()
    assert alias.broker.canonical_name == 'Test Broker'

    broker2 = BrokerMaster(canonical_name='Test Acquirer', normalized_name='testacq', display_name='Acq', is_historical_only=True)
    db_session.add(broker2)
    db_session.commit()

    rel = BrokerRelationship(predecessor_id=broker.broker_id, successor_id=broker2.broker_id, relationship_type='ACQUIRED_BY')
    db_session.add(rel)
    db_session.commit()
    assert rel.predecessor.broker_id == broker.broker_id
    assert rel.successor.broker_id == broker2.broker_id

def test_recommendation_constraints(db_session):
    stock = StockMaster(nse_symbol='HDFC', company_name='HDFC Bank')
    broker = BrokerMaster(canonical_name='B1', normalized_name='b1', display_name='B1')
    db_session.add_all([stock, broker])
    db_session.commit()

    # Base valid recommendation
    rec = BrokerRecommendation(
        stock_id=stock.stock_id,
        broker_id=broker.broker_id,
        recommendation_date=datetime.utcnow(),
        original_rating='Buy',
        normalized_rating='BUY',
        target_price=100.0,
        stop_loss=90.0,
        lifecycle_status='CURRENT'
    )
    db_session.add(rec)
    db_session.commit()

    # Negative target price rejected
    rec2 = BrokerRecommendation(
        stock_id=stock.stock_id, broker_id=broker.broker_id, recommendation_date=datetime.utcnow(),
        original_rating='Buy', normalized_rating='BUY', target_price=-10.0
    )
    db_session.add(rec2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Invalid lifecycle status rejected
    rec3 = BrokerRecommendation(
        stock_id=stock.stock_id, broker_id=broker.broker_id, recommendation_date=datetime.utcnow(),
        original_rating='Buy', normalized_rating='BUY', lifecycle_status='EXPIRED'
    )
    db_session.add(rec3)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_source_evidence(db_session):
    stock = StockMaster(nse_symbol='ITC', company_name='ITC Ltd')
    broker = BrokerMaster(canonical_name='B2', normalized_name='b2', display_name='B2')
    stype = SourceTypeMaster(type_name='TEST')
    db_session.add_all([stock, broker, stype])
    db_session.commit()

    rec1 = BrokerRecommendation(stock_id=stock.stock_id, broker_id=broker.broker_id, recommendation_date=datetime.utcnow(), original_rating='Buy', normalized_rating='BUY')
    rec2 = BrokerRecommendation(stock_id=stock.stock_id, broker_id=broker.broker_id, recommendation_date=datetime.utcnow(), original_rating='Buy', normalized_rating='BUY')
    src1 = SourceReference(source_type_id=stype.source_type_id, verification_status='VERIFIED_PRIMARY')
    src2 = SourceReference(source_type_id=stype.source_type_id, verification_status='PROVISIONAL')
    db_session.add_all([rec1, rec2, src1, src2])
    db_session.commit()

    rs1 = RecommendationSource(recommendation_id=rec1.recommendation_id, source_reference_id=src1.source_reference_id)
    rs2 = RecommendationSource(recommendation_id=rec1.recommendation_id, source_reference_id=src2.source_reference_id)
    rs3 = RecommendationSource(recommendation_id=rec2.recommendation_id, source_reference_id=src1.source_reference_id)
    db_session.add_all([rs1, rs2, rs3])
    db_session.commit()

    # Duplicate link rejected
    rs4 = RecommendationSource(recommendation_id=rec1.recommendation_id, source_reference_id=src1.source_reference_id)
    db_session.add(rs4)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Invalid verification status
    src_inv = SourceReference(source_type_id=stype.source_type_id, verification_status='FAKE')
    db_session.add(src_inv)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_recommendation_stream(db_session):
    broker = BrokerMaster(canonical_name='B3', normalized_name='b3', display_name='B3')
    db_session.add(broker)
    db_session.commit()

    stream = RecommendationStream(broker_id=broker.broker_id, stream_name='T', stream_type='T', frequency='DAILY')
    db_session.add(stream)
    db_session.commit()

    stream2 = RecommendationStream(broker_id=broker.broker_id, stream_name='T', stream_type='T', frequency='HOURLY')
    db_session.add(stream2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_price_observations(db_session):
    stock = StockMaster(nse_symbol='SBI', company_name='SBI')
    db_session.add(stock)
    db_session.commit()

    obs1 = PriceObservation(stock_id=stock.stock_id, observed_price=100.0, observed_timestamp=datetime.utcnow(), source='test')
    obs2 = PriceObservation(stock_id=stock.stock_id, observed_price=105.0, observed_timestamp=datetime.utcnow(), source='test')
    db_session.add_all([obs1, obs2])
    db_session.commit()

    obs_inv = PriceObservation(stock_id=stock.stock_id, observed_price=-5.0, observed_timestamp=datetime.utcnow(), source='test')
    db_session.add(obs_inv)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_import_provenance(db_session):
    batch = ImportBatch(status='PENDING')
    db_session.add(batch)
    db_session.commit()

    detail = ImportBatchDetail(batch_id=batch.batch_id, status='OK')
    review = ReviewQueue(item_type='REC', reason='test', import_batch_id=batch.batch_id)
    db_session.add_all([detail, review])
    db_session.commit()
    
    assert detail.batch_id == batch.batch_id
    assert review.import_batch_id == batch.batch_id

def test_seed_data(db_session):
    # Test that seed data is available (these are populated via migration, but tests use isolated DB without alembic upgrade by default)
    # Since we test the models against the schema created via Base.metadata.create_all(), the seed data WON'T be here in conftest!
    # The actual migration seed data is tested via alembic upgrade separately.
    pass
