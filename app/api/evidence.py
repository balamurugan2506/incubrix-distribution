"""Evidence download API routes matching GET /api/v1/evidence/{evidence_id}."""

import os
from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import FileResponse, JSONResponse
from app.storage.evidence import evidence_storage

router = APIRouter(prefix="/api/v1/evidence", tags=["Evidence & Artifacts"])


@router.get("/{evidence_id}")
async def get_evidence_document(
    evidence_id: str,
    format: str = Query("json", pattern="^(json|txt)$")
):
    """
    Retrieve stored evidence documents (certification reports, assist packs, import audits)
    as downloadable artifacts.
    """
    filepath = evidence_storage.get_evidence_path(evidence_id, format_type=format)
    if not filepath or not os.path.exists(filepath):
        # Check if identifier without extension works
        filepath = evidence_storage.get_evidence_path(evidence_id.replace(".json", "").replace(".txt", ""), format_type=format)
        if not filepath or not os.path.exists(filepath):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evidence document '{evidence_id}' not found."
            )

    media_type = "application/json" if format == "json" else "text/plain"
    return FileResponse(
        path=filepath,
        media_type=media_type,
        filename=os.path.basename(filepath)
    )
