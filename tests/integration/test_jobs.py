"""Integration tests for background jobs runtime and webhook callbacks."""

import pytest
import asyncio
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
async def test_job_submission_and_completion():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. First create a test destination
        dest_payload = {
            "name": "Live Dev Community",
            "url": "http://localhost:8001/devto",
            "platform_key": "devto",
            "connector_key": "devto",
            "frequency_cap": 10
        }
        res_dest = await client.post(
            "/api/v1/destinations",
            json=dest_payload,
            headers={"Idempotency-Key": "job_test_dest_1"}
        )
        assert res_dest.status_code == 201
        dest_id = res_dest.json()["id"]

        # 2. Submit publication job -> 202 Accepted
        job_payload = {
            "destination_id": dest_id,
            "rendition": {
                "title": "Asynchronous Background Jobs in Distribution",
                "body": "Detailed discussion about background job processing and reliable queueing.",
                "tags": ["async", "fastapi"]
            },
            "connection": {
                "base_url": "http://localhost:8001/devto",
                "credentials": {"api_key": "valid_mock_key"}
            }
        }
        res_submit = await client.post(
            "/api/v1/jobs",
            json=job_payload,
            headers={"Idempotency-Key": "job_sub_key_1"}
        )
        assert res_submit.status_code == 202
        submit_data = res_submit.json()
        job_id = submit_data["job_id"]
        assert submit_data["status"] == "queued"

        # 3. Poll job status until complete (within 5 seconds)
        completed = False
        final_job = None
        for _ in range(25):
            await asyncio.sleep(0.1)
            res_poll = await client.get(f"/api/v1/jobs/{job_id}")
            assert res_poll.status_code == 200
            poll_data = res_poll.json()
            if poll_data["status"] in ("succeeded", "failed"):
                completed = True
                final_job = poll_data
                break

        assert completed is True
        assert final_job["status"] == "succeeded"
        assert final_job["progress"] == 100
        assert final_job["result"]["status"] == "published"
        assert "http" in final_job["result"]["live_url"]


@pytest.mark.asyncio
async def test_job_fails_on_policy_violation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create destination with self_promo_allowed=False
        dest_payload = {
            "name": "Strict Forum",
            "url": "http://localhost:8001/devto",
            "platform_key": "devto",
            "connector_key": "devto",
            "self_promo_allowed": False
        }
        res_dest = await client.post(
            "/api/v1/destinations",
            json=dest_payload,
            headers={"Idempotency-Key": "job_test_dest_2"}
        )
        dest_id = res_dest.json()["id"]

        # Submit self-promotional content
        job_payload = {
            "destination_id": dest_id,
            "rendition": {
                "title": "Buy Our Software Now",
                "body": "Special deal! Sign up today and use promo code INCUBRIX for 50% discount!"
            }
        }
        res_submit = await client.post(
            "/api/v1/jobs",
            json=job_payload,
            headers={"Idempotency-Key": "job_sub_key_2"}
        )
        assert res_submit.status_code == 202
        job_id = res_submit.json()["job_id"]

        # Poll status
        for _ in range(20):
            await asyncio.sleep(0.1)
            res_poll = await client.get(f"/api/v1/jobs/{job_id}")
            if res_poll.json()["status"] in ("succeeded", "failed"):
                break

        final_data = res_poll.json()
        assert final_data["status"] == "failed"
        assert final_data["error_code"] == "DEST_SPEC_VIOLATION"
        assert "self-promotional" in final_data["error_message"]
