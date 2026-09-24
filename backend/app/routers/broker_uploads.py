from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional

from app.database import get_db
from app.schemas.broker_upload import BrokerUploadOut
from app.services import broker_upload_service as svc
from app.services import broker_pdf_intake_service as intake

router = APIRouter(prefix="/api/broker-uploads", tags=["broker-uploads"])


@router.get("", response_model=List[BrokerUploadOut])
def list_uploads():
    return svc.list_uploads()


@router.post("", response_model=BrokerUploadOut)
async def create_upload(
    file: UploadFile = File(...),
    broker_name: str = Form(...),
    stock_symbol: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    discovery_source: Optional[str] = Form(None),
    discovery_url: Optional[str] = Form(None),
):
    content = await file.read(svc.MAX_FILE_SIZE_BYTES + 1)
    try:
        # Off the event loop: saving waits on the manifest lock and disk I/O.
        return await run_in_threadpool(
            svc.save_upload,
            broker_name=broker_name,
            original_filename=file.filename or "upload.pdf",
            content=content,
            content_type=file.content_type,
            stock_symbol=stock_symbol,
            note=note,
            discovery_source=discovery_source,
            discovery_url=discovery_url,
        )
    except svc.DuplicateUploadError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except svc.UploadStorageError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except svc.BrokerUploadError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/preview")
async def preview_upload(
    file: UploadFile = File(...),
    stock_symbol: Optional[str] = Form(None),
    discovery_source: Optional[str] = Form(None),
    discovery_url: Optional[str] = Form(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Read-only preview: nothing is stored, imported or written."""
    content = await file.read(svc.MAX_FILE_SIZE_BYTES + 1)
    try:
        # Off the event loop: the PDF is parsed in a separate, time-limited process.
        return await run_in_threadpool(
            intake.preview_pdf,
            db,
            content=content,
            original_filename=file.filename or "upload.pdf",
            content_type=file.content_type,
            stock_symbol_hint=stock_symbol,
            discovery_source=discovery_source,
            discovery_url=discovery_url,
        )
    except intake.PdfReadFailure as e:
        # Busy -> retry later; reader failure -> server-side; the PDF itself -> 400.
        status = {"BUSY": 503, "PARSER_FAILED": 500}.get(e.category, 400)
        raise HTTPException(status_code=status, detail=str(e))
    except svc.BrokerUploadError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{upload_id}/file")
def get_upload_file(upload_id: str):
    entry = svc.get_upload(upload_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Upload not found")
    path = svc.resolve_file_path(entry)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored file is missing on disk")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=entry["original_filename"],
    )
