from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from typing import List
import json

from app.database import get_db
from app.models import ImportBatch, ImportBatchDetail
from app.schemas.import_batch import (
    UploadResponse, MapRequest, PreviewResponse, ParsedImportRow, ImportBatchSummary
)
from app.services.import_service import ImportService

router = APIRouter(prefix="/api/imports", tags=["Imports"])

@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(('.csv', '.xlsx')):
        raise HTTPException(400, "Only .csv and .xlsx files are supported")
    
    contents = await file.read()
    try:
        headers, rows = ImportService.parse_file(contents, file.filename)
    except Exception as e:
        raise HTTPException(400, f"Error parsing file: {e}")
        
    if not rows:
        raise HTTPException(400, "File is empty")
        
    batch = ImportBatch(
        filename=file.filename,
        status="UPLOADED",
        total_rows=len(rows)
    )
    db.add(batch)
    db.flush()
    
    # Store raw rows temporarily in details
    for idx, row in enumerate(rows):
        detail = ImportBatchDetail(
            batch_id=batch.batch_id,
            row_number=idx + 1,
            status="UPLOADED",
            raw_data=json.dumps(row)
        )
        db.add(detail)
    db.commit()
    
    return UploadResponse(
        batch_id=batch.batch_id,
        filename=file.filename,
        detected_headers=headers,
        preview_rows=rows[:5]
    )

@router.post("/{batch_id}/mapping", response_model=PreviewResponse)
def apply_mapping(batch_id: int, req: MapRequest, db: Session = Depends(get_db)):
    batch = db.query(ImportBatch).filter(ImportBatch.batch_id == batch_id).first()
    if not batch:
        raise HTTPException(404, "Batch not found")
        
    details = db.query(ImportBatchDetail).filter(ImportBatchDetail.batch_id == batch_id).all()
    batch_fingerprints = set()
    
    preview_rows = []
    
    # Reset counts
    batch.total_rows = len(details)
    batch.accepted_rows = 0
    batch.rejected_rows = 0
    batch.duplicate_rows = 0
    batch.review_rows = 0
    
    for d in details:
        raw_row = json.loads(d.raw_data)
        mapped_data, action, error_msg = ImportService.normalize_row(db, raw_row, req.mapping)
        
        # Dedup
        if action in ("UNIQUE", "REVIEW_REQUIRED"):
            action, msg, linked_id = ImportService.deduplicate(db, mapped_data, action, batch_fingerprints)
            if msg:
                error_msg = msg
            if linked_id:
                d.recommendation_id = linked_id
                
        d.mapped_data = json.dumps(mapped_data)
        d.action = action
        d.error_message = error_msg
        d.status = "PREVIEW"
        
        preview_rows.append(ParsedImportRow(
            row_number=d.row_number,
            raw_data=raw_row,
            mapped_data=mapped_data,
            action=action,
            error_message=error_msg
        ))
        
        # update stats
        if action in ('UNIQUE', 'ATTACH_SOURCE'):
            batch.accepted_rows += 1
        elif action == 'INVALID':
            batch.rejected_rows += 1
        elif action in ('EXACT_DUPLICATE', 'DUPLICATE_IN_BATCH'):
            batch.duplicate_rows += 1
        else:
            batch.review_rows += 1
            
    batch.status = "PREVIEW"
    db.commit()
    
    return PreviewResponse(
        batch_id=batch.batch_id,
        total_rows=batch.total_rows,
        valid_unique=batch.accepted_rows,
        exact_duplicates=batch.duplicate_rows,
        probable_duplicates=len([r for r in preview_rows if r.action == 'PROBABLE_DUPLICATE']),
        review_required=batch.review_rows,
        rejected=batch.rejected_rows,
        rows=preview_rows
    )

@router.get("/{batch_id}/preview", response_model=PreviewResponse)
def get_preview(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(ImportBatch).filter(ImportBatch.batch_id == batch_id).first()
    if not batch:
        raise HTTPException(404)
    details = db.query(ImportBatchDetail).filter(ImportBatchDetail.batch_id == batch_id).all()
    rows = []
    for d in details:
        rows.append(ParsedImportRow(
            row_number=d.row_number,
            raw_data=json.loads(d.raw_data) if d.raw_data else {},
            mapped_data=json.loads(d.mapped_data) if d.mapped_data else {},
            action=d.action or "",
            error_message=d.error_message
        ))
    return PreviewResponse(
        batch_id=batch_id,
        total_rows=batch.total_rows,
        valid_unique=batch.accepted_rows,
        exact_duplicates=batch.duplicate_rows,
        probable_duplicates=len([r for r in rows if r.action == 'PROBABLE_DUPLICATE']),
        review_required=batch.review_rows,
        rejected=batch.rejected_rows,
        rows=rows
    )

@router.post("/{batch_id}/confirm")
def confirm_batch(batch_id: int, db: Session = Depends(get_db)):
    ImportService.confirm_batch(db, batch_id)
    return {"status": "success"}

@router.post("/{batch_id}/rollback")
def rollback_batch(batch_id: int, db: Session = Depends(get_db)):
    ImportService.rollback_batch(db, batch_id)
    return {"status": "success"}

@router.get("", response_model=List[ImportBatchSummary])
def list_batches(db: Session = Depends(get_db)):
    batches = db.query(ImportBatch).order_by(ImportBatch.import_date.desc()).all()
    return batches
