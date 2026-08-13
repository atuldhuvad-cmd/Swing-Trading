import pytest
from sqlalchemy.exc import IntegrityError
from app.models import BrokerRecommendation, SourceReference, RecommendationStatusHistory, StockMaster, BrokerMaster
from app.services.recommendation_service import RecommendationService
from app.schemas.recommendation import BrokerRecommendationCreate, SourceReferenceCreate
from datetime import datetime
from fastapi import HTTPException

def test_exact_duplicate_protection(db_session):
    # Setup
    stock = StockMaster(nse_symbol="DUP", company_name="Dup")
    broker = BrokerMaster(canonical_name="DupBroker", normalized_name="dupbroker", display_name="Dup")
    db_session.add_all([stock, broker])
    db_session.commit()

    date = datetime.utcnow()
    evidence = [SourceReferenceCreate(source_type_id=1, verification_status="VERIFIED_PRIMARY")]
    
    rec_in = BrokerRecommendationCreate(
        stock_id=stock.stock_id,
        broker_id=broker.broker_id,
        recommendation_date=date,
        original_rating="Buy",
        normalized_rating="BUY",
        evidence=evidence
    )

    # 39. Exact duplicate recommendation detected
    rec1 = RecommendationService.create_recommendation(db_session, rec_in)
    assert rec1.recommendation_id is not None

    with pytest.raises(HTTPException) as excinfo:
        RecommendationService.create_recommendation(db_session, rec_in)
    assert excinfo.value.status_code == 409

def test_supersession(db_session):
    stock = StockMaster(nse_symbol="SUP", company_name="Sup")
    broker = BrokerMaster(canonical_name="SupBroker", normalized_name="supbroker", display_name="Sup")
    db_session.add_all([stock, broker])
    db_session.commit()

    evidence = [SourceReferenceCreate(source_type_id=1, verification_status="VERIFIED_PRIMARY")]
    
    rec_old_in = BrokerRecommendationCreate(
        stock_id=stock.stock_id,
        broker_id=broker.broker_id,
        recommendation_date=datetime.utcnow(),
        original_rating="Hold",
        normalized_rating="HOLD",
        evidence=evidence
    )
    old_rec = RecommendationService.create_recommendation(db_session, rec_old_in)

    rec_new_in = BrokerRecommendationCreate(
        stock_id=stock.stock_id,
        broker_id=broker.broker_id,
        recommendation_date=datetime.utcnow(),
        original_rating="Buy",
        normalized_rating="BUY",
        evidence=evidence
    )

    # 42. New broker recommendation can supersede old
    # 43. Old recommendation remains in database
    # 44. Status history created
    new_rec = RecommendationService.supersede_recommendation(db_session, old_rec.recommendation_id, rec_new_in)
    
    assert new_rec.recommendation_id != old_rec.recommendation_id
    
    db_session.refresh(old_rec)
    assert old_rec.lifecycle_status == "SUPERSEDED"
    assert old_rec.superseded_by_id == new_rec.recommendation_id
    
    history = db_session.query(RecommendationStatusHistory).filter(RecommendationStatusHistory.recommendation_id == old_rec.recommendation_id).order_by(RecommendationStatusHistory.changed_at.desc()).first()
    assert history.status == "SUPERSEDED"
