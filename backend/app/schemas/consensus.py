from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

class SourceReferenceOut(BaseModel):
    source_reference_id: int
    source_type_id: int
    publication_name: Optional[str] = None
    url: Optional[str] = None
    source_date: Optional[datetime] = None
    verification_status: str
    reliability_score: Optional[float] = None
    verification_notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class BrokerContributorOut(BaseModel):
    recommendation_id: int
    broker_id: int
    broker_canonical_name: str
    broker_display_name: str
    recommendation_date: datetime
    original_rating: str
    normalized_rating: str
    recommended_price: Optional[float] = None
    entry_price_low: Optional[float] = None
    entry_price_high: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    analyst_name: Optional[str] = None
    lifecycle_status: str
    age_days: int
    freshness_category: str
    verification_status: str
    sources: List[SourceReferenceOut] = []

    model_config = ConfigDict(from_attributes=True)

class RatingBreakdownItem(BaseModel):
    rating: str
    count: int
    percentage: float

class ConsensusMetricsOut(BaseModel):
    unique_broker_count: int
    bullish_broker_count: int
    bullish_percentage: float
    total_target_count: int
    target_coverage_pct: float
    min_target: Optional[float] = None
    max_target: Optional[float] = None
    avg_target: Optional[float] = None
    median_target: Optional[float] = None
    cmp: Optional[float] = None
    avg_target_upside_pct: Optional[float] = None
    median_target_upside_pct: Optional[float] = None
    avg_age_days: Optional[float] = None
    freshness_summary: str
    rec_count_7d: int = 0
    rec_count_14d: int = 0
    rec_count_30d: int = 0

class StockConsensusOut(BaseModel):
    stock_id: int
    nse_symbol: str
    bse_symbol: Optional[str] = None
    company_name: str
    isin: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap_category: Optional[str] = None
    listing_status: str
    cmp: Optional[float] = None
    cmp_updated_at: Optional[datetime] = None
    metrics: ConsensusMetricsOut
    rating_breakdown: List[RatingBreakdownItem] = []
    contributors: List[BrokerContributorOut] = []

class CandidateConsensusSummaryOut(BaseModel):
    stock_id: int
    nse_symbol: str
    company_name: str
    sector: Optional[str] = None
    cmp: Optional[float] = None
    unique_broker_count: int
    bullish_broker_count: int
    bullish_percentage: float
    avg_target: Optional[float] = None
    median_target: Optional[float] = None
    avg_target_upside_pct: Optional[float] = None
    median_target_upside_pct: Optional[float] = None
    target_coverage_pct: float
    rec_count_30d: int
    avg_age_days: Optional[float] = None
    freshness_summary: str
    latest_rec_date: Optional[datetime] = None

class CandidateListResponse(BaseModel):
    total: int
    items: List[CandidateConsensusSummaryOut]
