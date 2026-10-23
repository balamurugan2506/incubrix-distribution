"""Certification API routes under /api/v1/certification."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.destination import DestinationModel
from app.models.certification import CertificationRecordModel
from app.schemas.connector import ConnectionSchema
from app.certification.harness import harness, CertificationReport
from app.storage.evidence import evidence_storage

router = APIRouter(prefix="/api/v1/certification", tags=["Certification Harness"])


class CertificationRunRequest(BaseModel):
    destination_id: str = Field(..., description="Destination ID to certify")
    connection: Optional[ConnectionSchema] = None
    environment: str = Field("mock", description="'mock' for local simulation, 'production' for real platform")


@router.post("/run", response_model=CertificationReport)
async def run_certification(
    payload: CertificationRunRequest,
    db: AsyncSession = Depends(get_db)
):
    """Executes the full 7-step certification harness for a destination."""
    stmt = select(DestinationModel).where(DestinationModel.id == payload.destination_id)
    dest = (await db.execute(stmt)).scalar_one_or_none()
    if not dest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Destination '{payload.destination_id}' not found"
        )

    report = await harness.run_certification(
        destination=dest,
        connection=payload.connection,
        environment=payload.environment
    )
    return report


@router.get("/evidence/{destination_id}")
async def list_certification_evidence(
    destination_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve historical certification receipts and evidence records for a destination."""
    stmt = select(CertificationRecordModel).where(
        CertificationRecordModel.destination_id == destination_id
    ).order_by(CertificationRecordModel.created_at.desc())

    res = await db.execute(stmt)
    records = res.scalars().all()
    return [
        {
            "id": r.id,
            "destination_id": r.destination_id,
            "connector_key": r.connector_key,
            "environment": r.environment,
            "passed": r.passed,
            "created_at": r.created_at.isoformat(),
            "evidence": r.evidence_json
        }
        for r in records
    ]


@router.get("/receipt/{certification_id}")
async def get_certification_receipt(certification_id: str):
    """Fetch raw evidence envelope for a specific certification run."""
    doc = evidence_storage.get_evidence(certification_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence receipt '{certification_id}' not found"
        )
    return doc
