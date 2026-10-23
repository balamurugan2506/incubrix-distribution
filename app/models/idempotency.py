"""Idempotency record model for persistent deduplication and replay protection."""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, DateTime, JSON
from app.database import Base


class IdempotencyRecordModel(Base):
    __tablename__ = "idempotency_records"

    idempotency_key = Column(String(128), primary_key=True, index=True)
    request_hash = Column(String(64), nullable=False)  # SHA-256 of request path + body
    status = Column(String(32), default="pending")  # pending, completed, failed
    response_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)
