from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime

class StockBase(BaseModel):
    nse_symbol: str = Field(..., max_length=50, description="NSE Symbol")
    bse_symbol: Optional[str] = Field(None, max_length=50)
    company_name: str = Field(..., max_length=255)
    isin: Optional[str] = Field(None, max_length=12)
    sector: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=100)
    market_cap_category: Optional[str] = Field(None, max_length=50)
    listing_status: str = Field(default="ACTIVE", max_length=50)

class StockCreate(StockBase):
    pass

class StockUpdate(BaseModel):
    nse_symbol: Optional[str] = Field(None, max_length=50)
    bse_symbol: Optional[str] = Field(None, max_length=50)
    company_name: Optional[str] = Field(None, max_length=255)
    isin: Optional[str] = Field(None, max_length=12)
    sector: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=100)
    market_cap_category: Optional[str] = Field(None, max_length=50)
    listing_status: Optional[str] = Field(None, max_length=50)

class StockOut(StockBase):
    stock_id: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)
