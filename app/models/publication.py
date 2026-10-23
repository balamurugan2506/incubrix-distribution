"""Publication history record for frequency capping and reconciliation."""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Text
from app.database import Base


class PublicationRecordModel(Base):
    __tablename__ = "publication_records"

    id = Column(String(64), primary_key=True, index=True)
    destination_id = Column(String(64), index=True, nullable=False)
    platform_post_id = Column(String(128), nullable=True)
    live_url = Column(String(512), nullable=True)
    status = Column(String(32), default="published")
    rendition_title = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
