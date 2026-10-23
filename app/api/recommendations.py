"""Recommendations API endpoints under /api/v1/recommendations."""

from typing import List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.destination import DestinationModel
from app.catalogue.recommender import (
    recommender_engine,
    ContentItemSchema,
    DestinationRecommendation
)

router = APIRouter(prefix="/api/v1/recommendations", tags=["Recommendations"])


class RecommendationRequest(ContentItemSchema):
    limit: int = Field(default=10, ge=1, le=50)


@router.post("", response_model=List[DestinationRecommendation])
async def get_destination_recommendations(
    request: RecommendationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Rank candidate destinations for a content item.
    Excludes demoted, disabled, catalogue-only, and rule-blocked destinations.
    """
    stmt = select(DestinationModel).where(
        DestinationModel.status != "demoted",
        DestinationModel.enabled == True,  # noqa: E712
        DestinationModel.catalogue_only == False  # noqa: E712
    )
    result = await db.execute(stmt)
    destinations = list(result.scalars().all())

    recommendations = await recommender_engine.rank_destinations(
        content=request,
        destinations=destinations,
        db=db,
        limit=request.limit
    )
    return recommendations
