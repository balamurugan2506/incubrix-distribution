"""Certification evidence record model."""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, JSON, Text
from app.database import Base


class CertificationRecordModel(Base):
    __tablename__ = "certification_records"

    id = Column(String(64), primary_key=True, index=True)
    destination_id = Column(String(64), index=True, nullable=False)
    connector_key = Column(String(64), nullable=False)
    environment = Column(String(32), default="mock")  # mock or production
    passed = Column(Boolean, default=False)
    evidence_json = Column(JSON, default=dict)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
