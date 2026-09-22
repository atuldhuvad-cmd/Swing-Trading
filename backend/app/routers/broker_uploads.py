from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from typing import List, Optional

from app.schemas.broker_upload import BrokerUploadOut
from app.services import broker_upload_service as svc

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
):
    content = await file.read(svc.MAX_FILE_SIZE_BYTES + 1)
    try:
        return svc.save_upload(
            broker_name=broker_name,
            original_filename=file.filename or "upload.pdf",
            content=content,
            content_type=file.content_type,
            stock_symbol=stock_symbol,
            note=note,
        )
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
