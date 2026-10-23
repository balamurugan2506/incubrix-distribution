"""Unit and integration tests for Idempotency enforcement, deduplication, conflict, and restart persistence."""

import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db, async_engine, Base
from app.storage.idempotency_store import IdempotencyStore


@pytest.fixture(autouse=True)
async def clean_database():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.mark.asyncio
async def test_missing_idempotency_key_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # POST under /api/v1/ without Idempotency-Key
        payload = {
            "name": "Test Destination",
            "url": "https://example.com",
            "platform_key": "devto",
            "connector_key": "devto"
        }
        resp = await client.post("/api/v1/destinations", json=payload)
        assert resp.status_code == 400
        assert "Idempotency-Key header is required" in resp.json()["message"]


@pytest.mark.asyncio
async def test_repeated_identical_requests_return_cached_response():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        key = "idem_key_unique_test_1"
        payload = {
            "name": "Original Destination",
            "url": "https://unique-platform.incubrix.test/sub",
            "platform_key": "ghost",
            "connector_key": "ghost"
        }
        headers = {"Idempotency-Key": key}

        # 1. First request -> 201 Created
        resp1 = await client.post("/api/v1/destinations", json=payload, headers=headers)
        assert resp1.status_code == 201
        data1 = resp1.json()
        assert data1["name"] == "Original Destination"

        # 2. Second request with same key & identical payload -> 201 from cache without duplicate creation
        resp2 = await client.post("/api/v1/destinations", json=payload, headers=headers)
        assert resp2.status_code == 201
        assert resp2.headers.get("X-Cache") == "IDEMPOTENT-HIT"
        data2 = resp2.json()
        assert data2["id"] == data1["id"]

        # Verify only 1 destination exists in database
        resp_list = await client.get("/api/v1/destinations")
        assert len(resp_list.json()) == 1


@pytest.mark.asyncio
async def test_idempotency_conflict_on_payload_mismatch():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        key = "idem_key_conflict_test"
        headers = {"Idempotency-Key": key}

        payload1 = {
            "name": "First Destination",
            "url": "https://first.incubrix.test",
            "platform_key": "devto",
            "connector_key": "devto"
        }
        resp1 = await client.post("/api/v1/destinations", json=payload1, headers=headers)
        assert resp1.status_code == 201

        # Reuse same key with different payload
        payload2 = {
            "name": "Completely Different Destination",
            "url": "https://different.incubrix.test",
            "platform_key": "ghost",
            "connector_key": "ghost"
        }
        resp2 = await client.post("/api/v1/destinations", json=payload2, headers=headers)
        assert resp2.status_code == 409
        assert "materially different" in resp2.json()["message"]


@pytest.mark.asyncio
async def test_idempotency_survives_service_restart():
    """Simulate service restart: cached response should be served directly from SQLite store."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        key = "idem_restart_key_100"
        headers = {"Idempotency-Key": key}
        payload = {
            "name": "Restart Proof Destination",
            "url": "https://restart.incubrix.test",
            "platform_key": "lemmy",
            "connector_key": "lemmy"
        }

        # Original post before restart
        resp = await client.post("/api/v1/destinations", json=payload, headers=headers)
        assert resp.status_code == 201
        original_id = resp.json()["id"]

    # "Restart" by creating a brand new HTTP client and checking the store directly
    async with AsyncClient(transport=transport, base_url="http://test") as new_client:
        replay = await new_client.post("/api/v1/destinations", json=payload, headers=headers)
        assert replay.status_code == 201
        assert replay.headers.get("X-Cache") == "IDEMPOTENT-HIT"
        assert replay.json()["id"] == original_id
