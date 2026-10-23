"""Asynchronous job tracking model."""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, JSON, Text
from app.database import Base


class JobRecordModel(Base):
    __tablename__ = "jobs"

    job_id = Column(String(64), primary_key=True, index=True)
    destination_id = Column(String(64), nullable=True)
    status = Column(String(32), default="queued", index=True)  # queued, running, succeeded, failed
    progress = Column(Integer, default=0)  # 0 to 100
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    result = Column(JSON, default=dict)
    callback_url = Column(String(512), nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
