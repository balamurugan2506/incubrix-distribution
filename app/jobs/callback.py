"""HMAC-SHA256 signed callback dispatcher for background job completion."""

import json
import time
import httpx
from typing import Dict, Any, Optional
from app.connectors.signed_webhook import compute_hmac_signature
from app.config import settings
from app.logging_conf import logger


async def dispatch_job_callback(
    callback_url: str,
    job_id: str,
    status: str,
    result: Optional[Dict[str, Any]] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    secret: Optional[str] = None
) -> bool:
    """Send an HMAC-signed POST request to the client callback URL."""
    if not callback_url:
        return False

    hmac_secret = secret or settings.INCUBRIX_WEBHOOK_SECRET
    timestamp = str(int(time.time()))

    payload = {
        "event": "incubrix.job_update",
        "job_id": job_id,
        "status": status,
        "timestamp": timestamp,
        "result": result or {},
        "error_code": error_code,
        "error_message": error_message
    }

    body_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    signature = compute_hmac_signature(hmac_secret, body_bytes, timestamp)

    headers = {
        "Content-Type": "application/json",
        "X-IncuBrix-Signature": signature,
        "X-IncuBrix-Timestamp": timestamp,
        "User-Agent": "IncuBrix-Job-Notifier/1.0"
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.post(callback_url, content=body_bytes, headers=headers)
            logger.info(f"Callback dispatched to {callback_url} for job {job_id}: HTTP {resp.status_code}")
            return resp.status_code < 400
        except Exception as exc:
            logger.warning(f"Failed to deliver callback to {callback_url} for job {job_id}: {str(exc)}")
            return False
