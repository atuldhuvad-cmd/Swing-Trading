from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime

# Upload Response
class UploadResponse(BaseModel):
    batch_id: int
    filename: str
    detected_headers: List[str]
    preview_rows: List[Dict[str, Any]]

# Mapping payload from frontend
class ColumnMapping(BaseModel):
    # Mapping of canonical internal fields to the CSV headers
    nse_symbol: Optional[str] = None
    broker_name: Optional[str] = None
    recommendation_date: Optional[str] = None
    original_rating: Optional[str] = None
    recommended_price: Optional[str] = None
    entry_price_low: Optional[str] = None
    entry_price_high: Optional[str] = None
    target_price: Optional[str] = None
    stop_loss: Optional[str] = None
    time_horizon: Optional[str] = None
    expected_end_date: Optional[str] = None
    analyst_name: Optional[str] = None
    currency: Optional[str] = None
    stream_name: Optional[str] = None
    source_type: Optional[str] = None
    default_source_type: Optional[str] = None  # applied to every row when no source_type column is mapped
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    source_date: Optional[str] = None
    verification_status: Optional[str] = None
    original_text: Optional[str] = None

class MapRequest(BaseModel):
    mapping: ColumnMapping

# Preview and Detail
class ParsedImportRow(BaseModel):
    row_number: int
    raw_data: Dict[str, Any]
    mapped_data: Dict[str, Any]
    action: str  # EXACT_DUPLICATE, ATTACH_SOURCE, PROBABLE_DUPLICATE, POSSIBLE_UPDATE, UNIQUE, UNKNOWN_STOCK, UNKNOWN_BROKER, AMBIGUOUS_BROKER, INVALID
    error_message: Optional[str] = None

class PreviewResponse(BaseModel):
    batch_id: int
    total_rows: int
    valid_unique: int
    exact_duplicates: int
    probable_duplicates: int
    review_required: int
    rejected: int
    rows: List[ParsedImportRow]

class ImportBatchSummary(BaseModel):
    batch_id: int
    filename: Optional[str]
    import_date: datetime
    status: str
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    duplicate_rows: int
    review_rows: int
    
    class Config:
        orm_mode = True
        from_attributes = True

# Review Queue
class ReviewItem(BaseModel):
    review_id: int
    item_type: str
    item_reference_id: Optional[int]
    reason: str
    status: str
    created_at: datetime
    raw_data: Optional[Dict[str, Any]] = None
    mapped_data: Optional[Dict[str, Any]] = None
    batch_id: Optional[int] = None
    
    class Config:
        orm_mode = True
        from_attributes = True

class ReviewResolveRequest(BaseModel):
    action: str  # ACCEPT_AS_NEW, MERGE, REJECT, RESOLVE_BROKER
    resolved_broker_id: Optional[int] = None
    notes: Optional[str] = None
