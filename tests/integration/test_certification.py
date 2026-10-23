"""Integration tests for the 7-step publication certification harness."""

import pytest
import httpx
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import async_engine, Base
from mock_platforms.server import mock_app


@pytest.fixture(autouse=True)
async def setup_db_and_mock(monkeypatch):
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Route outbound httpx to mock_app
    real_async_client = httpx.AsyncClient

    def custom_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.ASGITransport(app=mock_app)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", custom_async_client)
    yield


@pytest.mark.asyncio
async def test_full_7_step_certification_run():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create a Dev.to test destination
        dest_payload = {
            "name": "Dev.to Certification Candidate",
            "url": "http://localhost:8001/devto",
            "platform_key": "devto",
            "connector_key": "devto",
            "frequency_cap": 10
        }
        res_dest = await client.post(
            "/api/v1/destinations",
            json=dest_payload,
            headers={"Idempotency-Key": "cert_test_dest_1"}
        )
        assert res_dest.status_code == 201
        dest_id = res_dest.json()["id"]

        # 2. Run certification
        cert_payload = {
            "destination_id": dest_id,
            "connection": {
                "base_url": "http://localhost:8001/devto",
                "credentials": {"api_key": "valid_mock_key"}
            },
            "environment": "mock"
        }
        res_cert = await client.post(
            "/api/v1/certification/run",
            json=cert_payload,
            headers={"Idempotency-Key": "cert_run_key_1"}
        )
        assert res_cert.status_code == 200
        report = res_cert.json()

        # Verify all 7 steps executed successfully
        assert report["passed"] is True
        assert report["destination_id"] == dest_id
        assert report["environment"] == "mock"
        assert report["connector_key"] == "devto"
        assert report["deletion_confirmed"] is True
        assert report["evidence_file"] is not None
        assert len(report["steps"]) >= 5

        # 3. Retrieve evidence history for destination
        res_evidence = await client.get(f"/api/v1/certification/evidence/{dest_id}")
        assert res_evidence.status_code == 200
        history = res_evidence.json()
        assert len(history) == 1
        assert history[0]["id"] == report["certification_id"]
        assert history[0]["passed"] is True

        # 4. Fetch raw evidence receipt
        cert_id = report["certification_id"]
        res_receipt = await client.get(f"/api/v1/certification/receipt/{cert_id}")
        assert res_receipt.status_code == 200
        envelope = res_receipt.json()
        assert envelope["evidence_id"] == cert_id
        assert envelope["payload"]["passed"] is True

        # 5. Verify destination last_certified_at was populated
        res_dest_updated = await client.get(f"/api/v1/destinations/{dest_id}")
        assert res_dest_updated.json()["last_certified_at"] is not None


@pytest.mark.asyncio
async def test_assisted_destination_certification():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create Assisted destination
        dest_payload = {
            "name": "Manual Reddit Sub",
            "url": "https://reddit.com/r/example",
            "platform_key": "assisted",
            "connector_key": "assisted",
            "automation_allowed": False
        }
        res_dest = await client.post(
            "/api/v1/destinations",
            json=dest_payload,
            headers={"Idempotency-Key": "cert_test_dest_2"}
        )
        dest_id = res_dest.json()["id"]

        # Run certification for assisted
        cert_payload = {
            "destination_id": dest_id,
            "environment": "mock"
        }
        res_cert = await client.post(
            "/api/v1/certification/run",
            json=cert_payload,
            headers={"Idempotency-Key": "cert_run_key_2"}
        )
        assert res_cert.status_code == 200
        report = res_cert.json()
        assert report["passed"] is True
        assert report["steps"][0]["step"] == "assisted_mode_verification"
