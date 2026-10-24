"""Evidence download API routes matching GET /api/v1/evidence/{evidence_id}."""

import os
from fastapi import APIRouter, HTTPException, status, Query, Response
from fastapi.responses import FileResponse, RedirectResponse
from app.storage.evidence import evidence_storage

router = APIRouter(prefix="/api/v1/evidence", tags=["Evidence & Artifacts"])


@router.get("/{evidence_id}")
async def get_evidence_document(
    evidence_id: str,
    format: str = Query("json", pattern="^(json|txt)$"),
    redirect_s3: bool = Query(False)
):
    """
    Retrieve stored evidence documents (certification reports, assist packs, import audits)
    as downloadable artifacts from S3/MinIO or local storage.
    """
    clean_id = evidence_id.replace(".json", "").replace(".txt", "")

    # Optional direct redirect to presigned S3 URL
    if redirect_s3 and evidence_storage.is_s3_active():
        presigned = evidence_storage.get_presigned_url(f"evidence/{clean_id}.{format}")
        if presigned:
            return RedirectResponse(url=presigned, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    # Check local disk first for zero-latency streaming
    filepath = evidence_storage.get_evidence_path(clean_id, format_type=format)
    if filepath and os.path.exists(filepath):
        media_type = "application/json" if format == "json" else "text/plain"
        return FileResponse(
            path=filepath,
            media_type=media_type,
            filename=os.path.basename(filepath)
        )

    # Check S3 backend bytes
    s3_data = evidence_storage.get_evidence_bytes(clean_id, format_type=format)
    if s3_data:
        raw_bytes, media_type = s3_data
        return Response(
            content=raw_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{clean_id}.{format}"'}
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Evidence document '{evidence_id}' not found in local or S3 storage."
    )
