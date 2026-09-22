from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models import BrokerRecommendation, SourceReference, RecommendationSource, RecommendationStatusHistory
from app.schemas.recommendation import BrokerRecommendationCreate
from datetime import datetime
import hashlib
from fastapi import HTTPException

class RecommendationService:
    @staticmethod
    def _generate_fingerprint(rec: BrokerRecommendation) -> str:
        # Generate a unique fingerprint based on stock, broker, date, and rating
        # to prevent exact duplicates.
        base_string = f"{rec.stock_id}-{rec.broker_id}-{rec.recommendation_date.isoformat()}-{rec.normalized_rating}"
        return hashlib.sha256(base_string.encode()).hexdigest()

    @staticmethod
    def _create_recommendation_internal(db: Session, rec_in: BrokerRecommendationCreate) -> BrokerRecommendation:
        """
        Adds a recommendation and its evidence sources to the session WITHOUT
        committing. Caller owns the transaction (commit/rollback) so this can
        be composed atomically with other writes, e.g. supersede_recommendation.
        Raises HTTPException(409) on an exact duplicate; other DB errors
        propagate to the caller uncaught.
        """
        # 1. Create the base recommendation object
        rec_dict = rec_in.model_dump(exclude={'evidence'})

        new_rec = BrokerRecommendation(**rec_dict)
        new_rec.fingerprint = RecommendationService._generate_fingerprint(new_rec)

        # 2. Check for exact duplicate
        existing_rec = db.query(BrokerRecommendation).filter(BrokerRecommendation.fingerprint == new_rec.fingerprint).first()
        if existing_rec:
            raise HTTPException(status_code=409, detail=f"Exact recommendation duplicate already exists with ID {existing_rec.recommendation_id}")

        db.add(new_rec)
        db.flush() # Get recommendation_id

        # 3. Create Status History
        history = RecommendationStatusHistory(
            recommendation_id=new_rec.recommendation_id,
            status=new_rec.lifecycle_status,
            changed_at=datetime.utcnow(),
            notes="Initial creation"
        )
        db.add(history)

        # 4. Attach Evidence Sources
        for evidence_in in rec_in.evidence:
            source_ref = SourceReference(**evidence_in.model_dump())
            db.add(source_ref)
            db.flush() # Get source_reference_id

            rec_source = RecommendationSource(
                recommendation_id=new_rec.recommendation_id,
                source_reference_id=source_ref.source_reference_id
            )
            db.add(rec_source)

        return new_rec

    @staticmethod
    def create_recommendation(db: Session, rec_in: BrokerRecommendationCreate):
        """
        Atomically creates a recommendation and its evidence sources.
        """
        try:
            new_rec = RecommendationService._create_recommendation_internal(db, rec_in)
            db.commit()
            db.refresh(new_rec)
            return new_rec
        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=422, detail=f"Failed to create recommendation: {str(e)}")

    @staticmethod
    def supersede_recommendation(db: Session, old_rec_id: int, new_rec_in: BrokerRecommendationCreate):
        """
        Creates a new recommendation and supersedes the old one.
        Must be atomic.
        """
        old_rec = db.query(BrokerRecommendation).filter(BrokerRecommendation.recommendation_id == old_rec_id).first()
        if not old_rec:
            raise HTTPException(status_code=404, detail="Old recommendation not found")
            
        if old_rec.broker_id != new_rec_in.broker_id or old_rec.stock_id != new_rec_in.stock_id:
            raise HTTPException(status_code=422, detail="Superseding recommendation must belong to the same broker and stock")

        try:
            # Create the new recommendation on the SAME transaction (no intermediate
            # commit) so a failure below rolls back the new recommendation too,
            # instead of leaving it committed while the old one stays CURRENT.
            new_rec = RecommendationService._create_recommendation_internal(db, new_rec_in)
            
            # Update old recommendation
            old_rec.lifecycle_status = "SUPERSEDED"
            old_rec.superseded_by_id = new_rec.recommendation_id
            old_rec.superseded_timestamp = datetime.utcnow()
            
            # Add status history for old recommendation
            history = RecommendationStatusHistory(
                recommendation_id=old_rec.recommendation_id,
                status="SUPERSEDED",
                changed_at=datetime.utcnow(),
                notes=f"Superseded by recommendation {new_rec.recommendation_id}"
            )
            db.add(history)
            
            db.commit()
            db.refresh(new_rec)
            return new_rec
            
        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=422, detail=f"Failed to supersede recommendation: {str(e)}")
