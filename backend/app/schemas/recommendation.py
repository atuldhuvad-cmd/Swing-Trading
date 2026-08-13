from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime

class SourceReferenceBase(BaseModel):
    source_type_id: int
    publication_name: Optional[str] = Field(None, max_length=255)
    url: Optional[str] = Field(None, max_length=1000)
    source_date: Optional[datetime] = None
    original_text: Optional[str] = None
    verification_status: str = Field(..., max_length=50)
    reliability_score: Optional[float] = None
    verification_notes: Optional[str] = None

class SourceReferenceCreate(SourceReferenceBase):
    pass

class SourceReferenceOut(SourceReferenceBase):
    source_reference_id: int
    collection_timestamp: Optional[datetime]
    verified_by: Optional[str]
    verified_at: Optional[datetime]
    import_batch_id: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


class BrokerRecommendationBase(BaseModel):
    stock_id: int
    broker_id: int
    stream_id: Optional[int] = None
    recommendation_date: datetime
    original_rating: str = Field(..., max_length=100)
    normalized_rating: str = Field(..., max_length=100)
    recommended_price: Optional[float] = None
    entry_price_low: Optional[float] = None
    entry_price_high: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    time_horizon_text: Optional[str] = Field(None, max_length=100)
    normalized_horizon: Optional[str] = Field(None, max_length=50)
    expected_end_date: Optional[datetime] = None
    analyst_name: Optional[str] = Field(None, max_length=255)
    currency: Optional[str] = Field(None, max_length=10)
    lifecycle_status: str = Field(default="CURRENT", max_length=50)

class BrokerRecommendationCreate(BrokerRecommendationBase):
    evidence: List[SourceReferenceCreate] = Field(..., min_length=1, description="At least one piece of evidence is required.")

class BrokerRecommendationOut(BrokerRecommendationBase):
    recommendation_id: int
    superseded_by_id: Optional[int]
    superseded_timestamp: Optional[datetime]
    fingerprint: Optional[str]
    import_batch_id: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


class RecommendationStatusHistoryOut(BaseModel):
    history_id: int
    recommendation_id: int
    status: str
    changed_at: datetime
    notes: Optional[str]

    model_config = ConfigDict(from_attributes=True)

class RecommendationDetailOut(BrokerRecommendationOut):
    sources: List[SourceReferenceOut] = []
    status_history: List[RecommendationStatusHistoryOut] = []
