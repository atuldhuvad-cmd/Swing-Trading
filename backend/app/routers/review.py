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
            
            batch = db.query(ImportBatch).filter(ImportBatch.batch_id == detail.batch_id).first()
            if batch and batch.status in ('COMPLETED', 'PREVIEW'):
                mapped = json.loads(detail.mapped_data)
                if req.resolved_broker_id:
                    mapped['broker_id'] = req.resolved_broker_id
                    detail.mapped_data = json.dumps(mapped)
                    
                ImportService.confirm_batch(db, detail.batch_id) 
                batch.review_rows = max(0, batch.review_rows - 1)
                
        item.status = 'RESOLVED_ACCEPTED'

    elif req.action == 'MERGE':
        pass # Simplified for now, similar logic to attach source
        item.status = 'RESOLVED_MERGED'
        
    db.commit()
    return {"status": "success"}
