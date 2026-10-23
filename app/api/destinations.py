"""Destination Catalogue API endpoints under /api/v1/destinations."""

import uuid
import asyncio
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database import get_db
from app.models.destination import DestinationModel
from app.schemas.destination import (
    DestinationCreate,
    DestinationUpdate,
    DestinationResponse,
    CSVImportSummary
)
from app.catalogue.csv_importer import normalise_url, import_destinations_from_csv
from app.api.jobs import JobSubmitResponse
from app.jobs.manager import job_manager

router = APIRouter(prefix="/api/v1/destinations", tags=["Destination Catalogue"])


@router.get("", response_model=List[DestinationResponse])
async def list_destinations(
    platform_key: Optional[str] = None,
    category: Optional[str] = None,
    enabled: Optional[bool] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(DestinationModel)
    if platform_key:
        stmt = stmt.where(DestinationModel.platform_key == platform_key)
    if category:
        stmt = stmt.where(DestinationModel.category == category)
    if enabled is not None:
        stmt = stmt.where(DestinationModel.enabled == enabled)

    stmt = stmt.offset(offset).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("", response_model=DestinationResponse, status_code=status.HTTP_201_CREATED)
async def create_destination(
    payload: DestinationCreate,
    db: AsyncSession = Depends(get_db)
):
    norm_url = normalise_url(payload.url)

    # Check for duplicate
    stmt = select(DestinationModel).where(
        DestinationModel.normalised_url == norm_url,
        DestinationModel.platform_key == payload.platform_key
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Destination with URL '{norm_url}' on platform '{payload.platform_key}' already exists."
        )

    dest_id = f"dest_{uuid.uuid4().hex[:12]}"
    dest = DestinationModel(
        id=dest_id,
        normalised_url=norm_url,
        **payload.model_dump()
    )
    db.add(dest)
    await db.commit()
    await db.refresh(dest)
    return dest


@router.get("/{destination_id}", response_model=DestinationResponse)
async def get_destination(
    destination_id: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(DestinationModel).where(DestinationModel.id == destination_id)
    dest = (await db.execute(stmt)).scalar_one_or_none()
    if not dest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Destination '{destination_id}' not found"
        )
    return dest


@router.put("/{destination_id}", response_model=DestinationResponse)
async def update_destination(
    destination_id: str,
    payload: DestinationUpdate,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(DestinationModel).where(DestinationModel.id == destination_id)
    dest = (await db.execute(stmt)).scalar_one_or_none()
    if not dest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Destination '{destination_id}' not found"
        )

    update_data = payload.model_dump(exclude_unset=True)
    if "url" in update_data:
        update_data["normalised_url"] = normalise_url(update_data["url"])

    for k, v in update_data.items():
        setattr(dest, k, v)

    await db.commit()
    await db.refresh(dest)
    return dest


@router.delete("/{destination_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_destination(
    destination_id: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(DestinationModel).where(DestinationModel.id == destination_id)
    dest = (await db.execute(stmt)).scalar_one_or_none()
    if not dest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Destination '{destination_id}' not found"
        )
    await db.delete(dest)
    await db.commit()
    return None


@router.post("/import-csv", response_model=CSVImportSummary)
async def import_csv(
    file: UploadFile = File(...),
    check_reachability: bool = Query(True),
    db: AsyncSession = Depends(get_db)
):
    content_bytes = await file.read()
    csv_text = content_bytes.decode("utf-8-sig", errors="replace")
    summary = await import_destinations_from_csv(csv_text, db, perform_reachability=check_reachability)
    return summary


@router.post("/import-csv-job", response_model=JobSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_csv_import_job(
    file: UploadFile = File(...),
    check_reachability: bool = Query(True),
    callback_url: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Submits CSV catalogue import as an asynchronous background job returning 202 Accepted and job_id."""
    content_bytes = await file.read()
    csv_text = content_bytes.decode("utf-8-sig", errors="replace")

    job = await job_manager.create_job(
        destination_id=None,
        callback_url=callback_url
    )

    asyncio.create_task(
        job_manager.run_csv_import_job(
            job_id=job.job_id,
            csv_text=csv_text,
            check_reachability=check_reachability,
            callback_url=callback_url
        )
    )

    return JobSubmitResponse(
        job_id=job.job_id,
        status="queued",
        progress=0,
        status_url=f"/api/v1/jobs/{job.job_id}"
    )
