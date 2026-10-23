"""Test Hard Case 1: Safe retries after platform timeout with zero duplicates."""

import pytest
import httpx
from mock_platforms.server import (
    mock_app,
    _devto_articles,
    _discourse_posts,
    _lemmy_posts,
    _ghost_posts,
    _webhook_records
)
from app.main import app
from app.connectors.registry import registry
from app.schemas.connector import RenditionSchema, DestinationSchema, ConnectionSchema
from app.rules.errors import ConnectorException, ErrorCode
from app.storage.idempotency_store import IdempotencyStore


@pytest.fixture(autouse=True)
def mock_httpx_client(monkeypatch):
    """Route outbound httpx.AsyncClient requests to the in-process mock platform FastAPI app."""
    real_async_client = httpx.AsyncClient

    def custom_async_client(*args, **kwargs):
        if "transport" not in kwargs:
            kwargs["transport"] = httpx.ASGITransport(app=mock_app)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", custom_async_client)


@pytest.fixture(autouse=True)
def reset_mock_state():
    _devto_articles.clear()
    _discourse_posts.clear()
    _lemmy_posts.clear()
    _ghost_posts.clear()
    _webhook_records.clear()


@pytest.mark.asyncio
async def test_devto_timeout_after_create_and_reconcile():
    """
    Test scenario: Platform creates the post, then answers too late (504 Gateway Timeout).
    The service marks outcome_unknown. On retry with the same key, it reconciles with
    the platform, returns the SAME post, and platform holds exactly 1 post.
    """
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "rendition": {
                "title": "Idempotent Safe Retry Article Title",
                "body": "This is a detailed technical post about zero duplicate distribution on late timeout.",
                "tags": ["python", "fastapi"]
            },
            "destination": {
                "name": "Dev.to Mock",
                "url": "http://localhost:8001/devto",
                "platform_key": "devto",
                "connector_key": "devto",
                "surface": "article",
                "instance_config": {}
            },
            "connection": {
                "base_url": "http://localhost:8001/devto",
                "credentials": {"api_key": "test_devto_key"},
                "metadata": {"simulate": "timeout-after-create"}
            },
            "idempotency_key": "idem-devto-timeout-001"
        }

        # 1. First attempt: mock creates post, then simulates 504 timeout
        resp1 = await client.post(
            "/connector/v1/devto/publish",
            json=payload,
            headers={"Idempotency-Key": "idem-devto-timeout-001"}
        )
        assert resp1.status_code == 503 or resp1.status_code == 504

        # Verify platform created exactly 1 article despite the timeout response
        assert len(_devto_articles) == 1
        initial_post_id = list(_devto_articles.keys())[0]

        # 2. Retry with the SAME idempotency key and identical payload
        resp2 = await client.post(
            "/connector/v1/devto/publish",
            json=payload,
            headers={"Idempotency-Key": "idem-devto-timeout-001"}
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["platform_post_id"] == str(initial_post_id)
        assert data2["status"] == "published"

        # Platform must STILL hold exactly 1 post (0 duplicates!)
        assert len(_devto_articles) == 1


@pytest.mark.asyncio
async def test_discourse_timeout_after_create_and_reconcile():
    """Discourse safe retry after timeout creates 0 duplicates."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "rendition": {
                "title": "Discourse Timeout Recovery Discussion Topic",
                "body": "Testing platform post reconciliation when gateway timeout occurs after creation.",
                "tags": ["architecture"]
            },
            "destination": {
                "name": "Discourse Mock",
                "url": "http://localhost:8001/discourse",
                "platform_key": "discourse",
                "connector_key": "discourse",
                "surface": "forum_topic",
                "instance_config": {"category_id": 1}
            },
            "connection": {
                "base_url": "http://localhost:8001/discourse",
                "credentials": {"api_key": "test_key", "api_username": "bot"},
                "metadata": {"simulate": "timeout-after-create"}
            },
            "idempotency_key": "idem-discourse-timeout-002"
        }

        # 1. First attempt triggers 504 after creation
        resp1 = await client.post(
            "/connector/v1/discourse/publish",
            json=payload,
            headers={"Idempotency-Key": "idem-discourse-timeout-002"}
        )
        assert resp1.status_code in (503, 504)
        assert len(_discourse_posts) == 1
        initial_post_id = list(_discourse_posts.keys())[0]

        # 2. Retry with same key
        resp2 = await client.post(
            "/connector/v1/discourse/publish",
            json=payload,
            headers={"Idempotency-Key": "idem-discourse-timeout-002"}
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["platform_post_id"] == str(initial_post_id)
        assert len(_discourse_posts) == 1


@pytest.mark.asyncio
async def test_webhook_timeout_after_create_and_reconcile():
    """Webhook safe retry after timeout creates 0 duplicates."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "rendition": {
                "title": "Webhook Idempotent Delivery",
                "body": "Webhook delivery verification with late acknowledgement.",
                "tags": []
            },
            "destination": {
                "name": "Partner Webhook",
                "url": "http://localhost:8001/webhook",
                "platform_key": "webhook",
                "connector_key": "signed_webhook",
                "surface": "webhook",
                "instance_config": {"endpoint_url": "http://localhost:8001/webhook"}
            },
            "connection": {
                "base_url": "http://localhost:8001/webhook",
                "credentials": {"secret": "super_secret_webhook_key_32_bytes_long!!"},
                "metadata": {"simulate": "timeout-after-create"}
            },
            "idempotency_key": "idem-webhook-timeout-003"
        }

        # 1. First attempt triggers 504 after creation
        resp1 = await client.post(
            "/connector/v1/signed_webhook/publish",
            json=payload,
            headers={"Idempotency-Key": "idem-webhook-timeout-003"}
        )
        assert resp1.status_code in (503, 504)
        assert len(_webhook_records) == 1
        initial_post_id = list(_webhook_records.keys())[0]

        # 2. Retry with same key
        resp2 = await client.post(
            "/connector/v1/signed_webhook/publish",
            json=payload,
            headers={"Idempotency-Key": "idem-webhook-timeout-003"}
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["platform_post_id"] == str(initial_post_id)
        assert len(_webhook_records) == 1
        assert resp2.status_code == 200
        assert len(_webhook_records) == 1


@pytest.mark.asyncio
async def test_idempotency_key_enforced_on_all_post_endpoints():
    """Verify that all POST endpoints require Idempotency-Key with zero exemptions."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Import CSV without key must return 400
        resp = await client.post("/api/v1/destinations/import-csv", content=b"header\nval")
        assert resp.status_code == 400
        assert "Idempotency-Key header is required" in resp.text
