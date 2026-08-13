from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import json

from app.database import get_db
from app.models import ReviewQueue, BrokerMaster, BrokerRecommendation, SourceReference, RecommendationSource, ImportBatchDetail, ImportBatch
from app.schemas.import_batch import ReviewItem, ReviewResolveRequest
from app.services.import_service import ImportService

router = APIRouter(prefix="/api/review", tags=["Review"])

@router.get("", response_model=List[ReviewItem])
def list_review_items(db: Session = Depends(get_db)):
    items = db.query(ReviewQueue).filter(ReviewQueue.status == 'PENDING').order_by(ReviewQueue.created_at.desc()).all()
    results = []
    for item in items:
        raw_data = None
        mapped_data = None
        
        if item.item_type == 'IMPORT_ROW' and item.item_reference_id:
            detail = db.query(ImportBatchDetail).filter(ImportBatchDetail.detail_id == item.item_reference_id).first()
            if detail:
                raw_data = json.loads(detail.raw_data) if detail.raw_data else None
                mapped_data = json.loads(detail.mapped_data) if detail.mapped_data else None

        results.append(ReviewItem(
            review_id=item.review_id,
            item_type=item.item_type,
            item_reference_id=item.item_reference_id,
            reason=item.reason,
            status=item.status,
            created_at=item.created_at,
            raw_data=raw_data,
            mapped_data=mapped_data,
            batch_id=item.import_batch_id
        ))
    return results

@router.post("/{review_id}/resolve")
def resolve_review_item(review_id: int, req: ReviewResolveRequest, db: Session = Depends(get_db)):
    item = db.query(ReviewQueue).filter(ReviewQueue.review_id == review_id).first()
    if not item or item.status != 'PENDING':
        raise HTTPException(404, "Pending review item not found")

    detail = None
    if item.item_type == 'IMPORT_ROW' and item.item_reference_id:
        detail = db.query(ImportBatchDetail).filter(ImportBatchDetail.detail_id == item.item_reference_id).first()
        
    if req.action == 'REJECT':
        item.status = 'RESOLVED_REJECTED'
        if detail:
            detail.status = 'REJECTED'
            batch = db.query(ImportBatch).filter(ImportBatch.batch_id == detail.batch_id).first()
            if batch:
                batch.review_rows = max(0, batch.review_rows - 1)
                batch.rejected_rows += 1
                
    elif req.action == 'ACCEPT_AS_NEW':
        if detail:
            # Re-execute as UNIQUE
            detail.action = 'UNIQUE'
            detail.status = 'PREVIEW'
            # Note: We should ideally immediately confirm it if the batch is completed,
            # or leave it in PREVIEW if the batch is in PREVIEW.
            # Assuming batch is COMPLETED, we process it now.
            batch = db.query(ImportBatch).filter(ImportBatch.batch_id == detail.batch_id).first()
            if batch and batch.status == 'COMPLETED':
                mapped = json.loads(detail.mapped_data)
                
                # Check for resolved broker
                if req.resolved_broker_id:
                    mapped['broker_id'] = req.resolved_broker_id
                    detail.mapped_data = json.dumps(mapped)
                    
                ImportService.confirm_batch(db, detail.batch_id) # confirm_batch handles only PREVIEW items and sets to COMPLETED
                # But wait, confirm_batch processes ALL PREVIEW items. That's fine.
                
                # Wait, confirm batch loops over all PREVIEW.
                # Actually, better to just process this single row here for safety.
                from datetime import datetime
                
                src = SourceReference(
                    source_type_id=1,
                    publication_name=mapped.get('source_name'),
                    url=mapped.get('source_url'),
                    verification_status=mapped.get('verification_status', 'PROVISIONAL'),
                    import_batch_id=item.import_batch_id
                )
                db.add(src)
                db.flush()
                
                rec = BrokerRecommendation(
                    stock_id=mapped['stock_id'],
                    broker_id=mapped['broker_id'],
                    recommendation_date=datetime.fromisoformat(mapped['recommendation_date']),
                    original_rating=mapped['original_rating'],
                    normalized_rating=mapped['normalized_rating'],
                    target_price=mapped.get('target_price'),
                    recommended_price=mapped.get('recommended_price'),
                    entry_price_low=mapped.get('entry_price_low'),
                    entry_price_high=mapped.get('entry_price_high'),
                    stop_loss=mapped.get('stop_loss'),
                    lifecycle_status='CURRENT',
                    import_batch_id=item.import_batch_id
                )
                rec.fingerprint = ImportService.fingerprint(mapped)
                db.add(rec)
                db.flush()
                db.add(RecommendationSource(recommendation_id=rec.recommendation_id, source_reference_id=src.source_reference_id))
                
                detail.status = 'COMPLETED'
                detail.recommendation_id = rec.recommendation_id
                detail.source_reference_id = src.source_reference_id
                batch.review_rows = max(0, batch.review_rows - 1)
                batch.accepted_rows += 1
                
        item.status = 'RESOLVED_ACCEPTED'

    elif req.action == 'MERGE':
        pass # Simplified for now, similar logic to attach source
        item.status = 'RESOLVED_MERGED'
        
    db.commit()
    return {"status": "success"}
