"""Unit tests verifying Integration Standard 5 structured error envelopes."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.rules.errors import ErrorCode, ConnectorException


@pytest.mark.asyncio
async def test_idempotency_missing_header_error_envelope():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # POST without Idempotency-Key
        resp = await client.post("/api/v1/destinations", json={})
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == ErrorCode.DEST_SPEC_VIOLATION.value
        assert "Idempotency-Key header is required" in data["error"]["message"]
        assert data["error"]["retryable"] is False
        assert "path" in data["error"]["details"]


@pytest.mark.asyncio
async def test_validation_error_envelope():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # POST invalid payload with required Idempotency-Key
        resp = await client.post(
            "/api/v1/destinations",
            json={"invalid_field": 123},
            headers={"Idempotency-Key": "test_err_val_1"}
        )
        assert resp.status_code == 422
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == ErrorCode.DEST_SPEC_VIOLATION.value
        assert data["error"]["message"] == "Request validation failed"
        assert data["error"]["retryable"] is False
        assert "errors" in data["error"]["details"]


@pytest.mark.asyncio
async def test_not_found_error_envelope():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/destinations/non_existent_dest_id")
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "NOT_FOUND"
        assert "not found" in data["error"]["message"]
        assert data["error"]["retryable"] is False


@pytest.mark.asyncio
async def test_connector_exception_envelope():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Calling publish with disabled destination or bad parameters
        resp = await client.post(
            "/connector/v1/lemmy/publish",
            json={
                "rendition": {"title": "Hi", "body": "Short"},
                "destination": {
                    "id": "d1",
                    "name": "Lemmy Test",
                    "url": "http://localhost:8536",
                    "platform_key": "lemmy",
                    "connector_key": "lemmy",
                    "surface": "community",
                    "instance_config": {}
                },
                "connection": {"base_url": "http://localhost:8536", "credentials": {}},
                "idempotency_key": "lemmy_err_test_1"
            }
        )
        assert resp.status_code in (400, 401, 422)
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] in [
            ErrorCode.DEST_SPEC_VIOLATION.value,
            ErrorCode.CONNECTION_AUTH_EXPIRED.value
        ]
        assert data["error"]["retryable"] is False
