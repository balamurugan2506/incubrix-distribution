"""Pydantic schemas for Destination catalogue operations and CSV import."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, ConfigDict


class DestinationBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    url: str = Field(..., min_length=4, max_length=512)
    platform_key: str = Field(..., min_length=2, max_length=64)
    connector_key: str = Field(..., min_length=2, max_length=64)
    surface: str = Field("main", max_length=64)
    category: str = Field("general", max_length=128)
    audience_tags: List[str] = Field(default_factory=list)
    language: str = Field("en", max_length=16)
    geo: str = Field("global", max_length=32)
    est_audience: int = Field(0, ge=0)
    rules_url: Optional[str] = Field(None, max_length=512)

    frequency_cap: int = Field(10, ge=0, description="Max allowed posts per 24 hours (0 = unlimited)")
    self_promo_allowed: bool = True
    link_policy: str = Field("allowed", description="allowed, restricted, or none")
    disclosure_required: bool = False
    automation_allowed: bool = True

    relevance_score: float = Field(3.0, ge=1.0, le=5.0)
    relevance_reason: Optional[str] = None
    level: str = Field("standard", description="core, tier2, experimental")
    enabled: bool = True
    instance_config: Dict[str, Any] = Field(default_factory=dict)


class DestinationCreate(DestinationBase):
    pass


class DestinationUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    surface: Optional[str] = None
    category: Optional[str] = None
    audience_tags: Optional[List[str]] = None
    language: Optional[str] = None
    geo: Optional[str] = None
    est_audience: Optional[int] = None
    rules_url: Optional[str] = None
    frequency_cap: Optional[int] = None
    self_promo_allowed: Optional[bool] = None
    link_policy: Optional[str] = None
    disclosure_required: Optional[bool] = None
    automation_allowed: Optional[bool] = None
    relevance_score: Optional[float] = None
    relevance_reason: Optional[str] = None
    level: Optional[str] = None
    enabled: Optional[bool] = None
    instance_config: Optional[Dict[str, Any]] = None


class DestinationResponse(DestinationBase):
    id: str
    normalised_url: str
    last_certified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CSVImportRowResult(BaseModel):
    row_number: int
    name: str
    url: str
    status: str  # imported, skipped_duplicate, error
    reason: Optional[str] = None


class CSVImportSummary(BaseModel):
    total_rows: int
    imported_count: int
    skipped_duplicates: int
    errors_count: int
    rows: List[CSVImportRowResult] = Field(default_factory=list)
