"""Integration test for Must-Have 7 (Secret Leak Prevention and Log Sanitization).

Verifies that publishing with high-entropy credentials/tokens in play never logs
Authorization headers, tokens, or secret keys, and that scripts/secret_scan.py
confirms the repository and logs remain clean.
"""

import io
import json
import logging
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.logging_conf import JSONFormatter, logger
from scripts.secret_scan import run_secret_scan


@pytest.mark.asyncio
async def test_publish_with_token_never_leaks_in_logs():
    """Verify that credentials provided in publish requests are never logged in plaintext."""
    test_secret_token = f"sensitive_token_{uuid.uuid4().hex}"
    test_api_key = f"sensitive_apikey_{uuid.uuid4().hex}"

    # Capture logs
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "rendition": {
                    "title": "Secret Prevention Audit",
                    "body": "Checking that credentials in headers or payload are never written to disk or logs.",
                    "tags": ["security", "audit"]
                },
                "destination": {
                    "name": "Audit Webhook",
                    "url": "http://localhost:8001/webhook",
                    "platform_key": "signed_webhook",
                    "connector_key": "signed_webhook",
                    "instance_config": {"endpoint_url": "http://localhost:8001/webhook"}
                },
                "connection": {
                    "credentials": {
                        "api_key": test_api_key,
                        "auth_token": test_secret_token,
                        "hmac_secret": test_secret_token
                    }
                },
                "idempotency_key": f"sec_audit_{uuid.uuid4().hex[:8]}"
            }

            headers = {
                "Idempotency-Key": payload["idempotency_key"],
                "Authorization": f"Bearer {test_secret_token}"
            }

            resp = await client.post("/connector/v1/signed_webhook/publish", json=payload, headers=headers)
            assert resp.status_code == 200

            handler.flush()
            log_output = log_capture.getvalue()

            # Critical assertions: The sensitive tokens must NEVER appear anywhere in the log output
            assert test_secret_token not in log_output, "CRITICAL: Secret token was leaked in application logs!"
            assert test_api_key not in log_output, "CRITICAL: API key was leaked in application logs!"
            assert "Bearer " + test_secret_token not in log_output, "CRITICAL: Authorization header leaked in logs!"

            # Run secret_scan with specific known secrets to verify repository and logs
            scan_report = run_secret_scan(known_secrets=[test_secret_token, test_api_key])
            assert scan_report["clean"] is True, f"Secret scan found leaks: {scan_report.get('findings')}"

    finally:
        root_logger.removeHandler(handler)
