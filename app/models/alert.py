"""SQLAlchemy model for Recertification and Operational Alerts."""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text
from app.database import Base


class AlertModel(Base):
    __tablename__ = "alerts"

    id = Column(String(64), primary_key=True)
    destination_id = Column(String(64), nullable=True)
    destination_name = Column(String(255), nullable=True)
    alert_type = Column(String(64), nullable=False)  # recertification_failed, demoted, schema_mismatch
    severity = Column(String(32), default="high")     # high, medium, low
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
