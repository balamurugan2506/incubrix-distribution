"""Alerts API endpoints under /api/v1/alerts."""

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.models.alert import AlertModel

router = APIRouter(prefix="/api/v1/alerts", tags=["Alerts"])


class AlertResponse(BaseModel):
    id: str
    destination_id: Optional[str] = None
    destination_name: Optional[str] = None
    alert_type: str
    severity: str
    message: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=List[AlertResponse])
async def list_alerts(
    destination_id: Optional[str] = Query(None, description="Filter by destination ID"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    severity: Optional[str] = Query(None, description="Filter by severity (high, medium, low)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve operational alerts such as recertification failures or schema demotions."""
    stmt = select(AlertModel).order_by(desc(AlertModel.created_at))
    if destination_id:
        stmt = stmt.where(AlertModel.destination_id == destination_id)
    if alert_type:
        stmt = stmt.where(AlertModel.alert_type == alert_type)
    if severity:
        stmt = stmt.where(AlertModel.severity == severity)

    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())
