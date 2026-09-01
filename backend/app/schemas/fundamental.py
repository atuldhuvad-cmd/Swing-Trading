from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FundamentalMetricIn(BaseModel):
    metric_name: str
    metric_value: Optional[str] = None
    status: str = "UNKNOWN"


class FundamentalManualImport(BaseModel):
    nse_symbol: str
    entity_type: str
    as_of_date: date
    financial_period: str
    period_type: str
    source_name: str
    source_reference: Optional[str] = None
    statement_scope: Optional[str] = None
    source_line_item: Optional[str] = None
    original_unit: Optional[str] = None
    metrics: List[FundamentalMetricIn] = Field(default_factory=list)


class FundamentalConfirmRequest(BaseModel):
    payload_sha256: str
    payload: FundamentalManualImport
