from datetime import datetime, timedelta
from app.models import SystemSetting, StockPrice, BrokerRecommendation, SourceReference, RecommendationSource, ImportBatch, ImportBatchDetail, StockMaster, BrokerMaster, SourceTypeMaster
from app.services.consensus_service import ConsensusService
from app.services.import_service import ImportService

def test_settings_validation_and_update(client, db_session):
    good={'fresh_max_days':7,'recent_max_days':15,'moderate_max_days':30,'stale_max_days':60,'universe_max_age_days':30,'eligible_normalized_ratings':['BUY','ADD']}
    assert client.put('/api/reference/settings',json=good).status_code==200
    assert db_session.get(SystemSetting,'UNIVERSE_MAX_AGE_DAYS').setting_value=='30'
    bad={**good,'recent_max_days':7}
    assert client.put('/api/reference/settings',json=bad).status_code==422

def test_stock_price_phase1_cache_fields(db_session):
    stock=db_session.query(StockMaster).first()
    row=StockPrice(stock_id=stock.stock_id,last_price=110,previous_price=100,price_change=10,percentage_change=10)
    db_session.add(row);db_session.commit()
    assert (row.previous_price,row.price_change,row.percentage_change)==(100,10,10)

def test_exact_freshness_boundaries(db_session):
    for key,value in [('FRESH_MAX_DAYS','7'),('RECENT_MAX_DAYS','15'),('MODERATE_MAX_DAYS','30'),('STALE_MAX_DAYS','60')]: db_session.merge(SystemSetting(setting_key=key,setting_value=value))
    db_session.commit(); now=datetime.utcnow()
    expected={0:'FRESH',7:'FRESH',8:'RECENT',15:'RECENT',16:'MODERATE',30:'MODERATE',31:'STALE',60:'STALE',61:'AGED'}
    stock=db_session.query(StockMaster).first(); broker=db_session.query(BrokerMaster).first(); st=db_session.query(SourceTypeMaster).first()
    for days,bucket in expected.items():
        rec=BrokerRecommendation(stock_id=stock.stock_id,broker_id=broker.broker_id,recommendation_date=now-timedelta(days=days),original_rating='BUY',normalized_rating='BUY',lifecycle_status='CURRENT',fingerprint=f'boundary-{days}')
        db_session.add(rec);db_session.flush();src=SourceReference(source_type_id=st.source_type_id,verification_status='VERIFIED_PRIMARY');db_session.add(src);db_session.flush();db_session.add(RecommendationSource(recommendation_id=rec.recommendation_id,source_reference_id=src.source_reference_id));db_session.commit()
        result=ConsensusService.get_latest_recommendations_per_broker(db_session,stock_id=stock.stock_id,lifecycle_status='CURRENT')
        assert result[0]['freshness_category']==bucket
        db_session.query(RecommendationSource).filter_by(recommendation_id=rec.recommendation_id).delete()
        db_session.delete(rec);db_session.delete(src);db_session.commit()

def test_rollback_preserves_preexisting_recommendation_and_source(db_session):
    stock=db_session.query(StockMaster).first(); broker=db_session.query(BrokerMaster).first(); st=db_session.query(SourceTypeMaster).first()
    pre=BrokerRecommendation(stock_id=stock.stock_id,broker_id=broker.broker_id,recommendation_date=datetime.utcnow(),original_rating='BUY',normalized_rating='BUY',lifecycle_status='CURRENT',fingerprint='pre')
    src=SourceReference(source_type_id=st.source_type_id,verification_status='VERIFIED_PRIMARY'); db_session.add_all([pre,src]);db_session.flush();db_session.add(RecommendationSource(recommendation_id=pre.recommendation_id,source_reference_id=src.source_reference_id))
    batch=ImportBatch(status='COMPLETED',filename='isolated.csv');db_session.add(batch);db_session.flush(); made=BrokerRecommendation(stock_id=stock.stock_id,broker_id=broker.broker_id,recommendation_date=datetime.utcnow()-timedelta(days=1),original_rating='BUY',normalized_rating='BUY',lifecycle_status='CURRENT',fingerprint='made',import_batch_id=batch.batch_id); made_src=SourceReference(source_type_id=st.source_type_id,verification_status='PROVISIONAL',import_batch_id=batch.batch_id);db_session.add_all([made,made_src]);db_session.flush();db_session.add(RecommendationSource(recommendation_id=made.recommendation_id,source_reference_id=made_src.source_reference_id));db_session.commit()
    made_id=made.recommendation_id
    ImportService.rollback_batch(db_session,batch.batch_id)
    assert db_session.query(BrokerRecommendation).filter_by(recommendation_id=pre.recommendation_id).one()
    assert db_session.query(SourceReference).filter_by(source_reference_id=src.source_reference_id).one()
    assert db_session.query(BrokerRecommendation).filter_by(recommendation_id=made_id).first() is None
