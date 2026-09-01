from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class OhlcvPreviewRow(BaseModel):
    trading_date: Optional[str] = None
    symbol: Optional[str] = None
    series: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    status: str
    message: Optional[str] = None

class OhlcvPreviewResponse(BaseModel):
    file_sha256: str
    original_filename: str
    rows_received: int
    rows_accepted: int
    rows_rejected: int
    rows_unmapped: int
    rows_ignored: int = 0
    rows_duplicates: int = 0
    rows_conflicts: int = 0
    preview_rows: List[OhlcvPreviewRow]

class OhlcvConfirmRequest(BaseModel):
    file_sha256: str
    original_filename: str
    source_name: str
    source_reference: Optional[str] = None

class DataImportBatchResponse(BaseModel):
    import_batch_id: int
    import_type: str
    status: str
    rows_accepted: int
    rows_rejected: int
    created_at: datetime
    class Config:
        orm_mode = True
