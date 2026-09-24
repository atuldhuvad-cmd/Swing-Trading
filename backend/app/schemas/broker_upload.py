from pydantic import BaseModel
from typing import Optional


class BrokerUploadOut(BaseModel):
    upload_id: str
    broker_name: str
    stock_symbol: Optional[str] = None
    note: Optional[str] = None
    original_filename: str
    size_bytes: int
    uploaded_at: str
    # Added later; entries stored before these existed simply omit them.
    sha256: Optional[str] = None
    discovery_source: Optional[str] = None
    discovery_url: Optional[str] = None
