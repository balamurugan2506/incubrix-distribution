"""Background Jobs API routes implementing POST /api/v1/jobs and GET /api/v1/jobs/{job_id}."""

import asyncio
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.job import JobRecordModel
from app.schemas.connector import RenditionSchema, ConnectionSchema
from app.jobs.manager import job_manager

router = APIRouter(prefix="/api/v1/jobs", tags=["Background Jobs"])


class JobSubmitRequest(BaseModel):
    destination_id: str = Field(..., description="Target destination ID from catalogue")
    rendition: RenditionSchema
    connection: Optional[ConnectionSchema] = None
    callback_url: Optional[str] = Field(None, description="Optional webhook URL for completion callback")


class JobSubmitResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    status_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    destination_id: Optional[str] = None
    status: str
    progress: int
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    result: Dict[str, Any] = Field(default_factory=dict)
    callback_url: Optional[str] = None


@router.post("", response_model=JobSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_job(
    payload: JobSubmitRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db)
):
    """Submit a long-running publication job. Returns HTTP 202 Accepted and job_id."""
    job = await job_manager.create_job(
        destination_id=payload.destination_id,
        callback_url=payload.callback_url
    )

    # Launch background execution task
    asyncio.create_task(
        job_manager.run_publication_job(
            job_id=job.job_id,
            destination_id=payload.destination_id,
            rendition=payload.rendition,
            connection=payload.connection,
            idempotency_key=idempotency_key,
            callback_url=payload.callback_url
        )
    )

    return JobSubmitResponse(
        job_id=job.job_id,
        status="queued",
        progress=0,
        status_url=f"/api/v1/jobs/{job.job_id}"
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve job progress (0-100), execution state, and live published links."""
    stmt = select(JobRecordModel).where(JobRecordModel.job_id == job_id)
    job = (await db.execute(stmt)).scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found"
        )

    return JobStatusResponse(
        job_id=job.job_id,
        destination_id=job.destination_id,
        status=job.status,
        progress=job.progress,
        error_code=job.error_code,
        error_message=job.error_message,
        result=job.result or {},
        callback_url=job.callback_url
    )
