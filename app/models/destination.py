"""Destination catalogue SQLAlchemy ORM model."""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, Float, DateTime, JSON, Text
from app.database import Base


class DestinationModel(Base):
    __tablename__ = "destinations"

    id = Column(String(64), primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    url = Column(String(512), nullable=False)
    normalised_url = Column(String(512), nullable=False, index=True)
    platform_key = Column(String(64), nullable=False, index=True)
    connector_key = Column(String(64), nullable=False)
    surface = Column(String(64), default="main")
    category = Column(String(128), default="general")
    audience_tags = Column(JSON, default=list)  # list of strings
    language = Column(String(16), default="en")
    geo = Column(String(32), default="global")
    est_audience = Column(Integer, default=0)
    rules_url = Column(String(512), nullable=True)

    # Posting rules parameters
    frequency_cap = Column(Integer, default=10)  # max posts per 24 hours
    self_promo_allowed = Column(Boolean, default=True)
    link_policy = Column(String(64), default="allowed")  # allowed, restricted, none
    disclosure_required = Column(Boolean, default=False)
    automation_allowed = Column(Boolean, default=True)

    # Scoring and quality
    relevance_score = Column(Float, default=3.0)
    relevance_reason = Column(Text, nullable=True)
    level = Column(String(32), default="standard")  # core, tier2, experimental

    # Operational status
    enabled = Column(Boolean, default=True)
    last_certified_at = Column(DateTime(timezone=True), nullable=True)
    instance_config = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
