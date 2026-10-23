"""Automated test suite verifying all 6 Core connectors against the mock platform server."""

import pytest
import httpx
from mock_platforms.server import mock_app
from app.connectors.registry import registry
from app.schemas.connector import (
    RenditionSchema,
    DestinationSchema,
    ConnectionSchema
)
from app.connectors.signed_webhook import compute_hmac_signature, verify_hmac_signature
from app.rules.errors import ConnectorException, ErrorCode


@pytest.fixture(autouse=True)
def mock_httpx_client(monkeypatch):
    """Route outbound httpx.AsyncClient requests to the in-process mock platform FastAPI app."""
    real_async_client = httpx.AsyncClient

    def custom_async_client(*args, **kwargs):
        # Override transport to route to mock_app
        transport = httpx.ASGITransport(app=mock_app)
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", custom_async_client)


@pytest.mark.asyncio
async def test_discourse_lifecycle():
    connector = registry.get_connector("discourse")

    rendition = RenditionSchema(
        title="Discourse Discussion: Advanced Distribution Architecture",
        body="This is an in-depth topic body explaining multi-destination distribution networks and connector runtimes.",
        tags=["architecture", "backend"]
    )
    dest = DestinationSchema(
        name="Tech Forum",
        url="http://localhost:8001/discourse",
        platform_key="discourse",
        connector_key="discourse",
        instance_config={"category_id": 5}
    )
    conn = ConnectionSchema(
        base_url="http://localhost:8001/discourse",
        credentials={"api_key": "test_key", "api_username": "incubrix_bot"}
    )

    # 1. Validate
    val = await connector.validate(rendition, dest, conn)
    assert val.ok is True

    # 2. Publish
    pub = await connector.publish(rendition, dest, conn, "idem_discourse_1")
    assert pub.platform_post_id != ""
    assert "topic" in pub.live_url
    assert pub.status == "published"

    # 3. Get Status
    status = await connector.get_status(pub.platform_post_id, conn)
    assert status.status == "published"
    assert "topic" in status.live_url

    # 4. Metrics
    metrics = await connector.fetch_metrics(pub.platform_post_id, conn)
    assert metrics.views >= 0
    assert metrics.likes >= 0

    # 5. Delete
    deleted = await connector.delete(pub.platform_post_id, conn)
    assert deleted.deleted is True


@pytest.mark.asyncio
async def test_lemmy_lifecycle():
    connector = registry.get_connector("lemmy")

    rendition = RenditionSchema(
        title="Lemmy Post: Long Tail Networks",
        body="Discussing federated content distribution using pure connector runtimes and posting rules.",
        canonical_url="https://incubrix.test/articles/fediverse"
    )
    dest = DestinationSchema(
        name="Lemmy Tech Community",
        url="http://localhost:8001/lemmy",
        platform_key="lemmy",
        connector_key="lemmy",
        instance_config={"community_id": 1}
    )
    conn = ConnectionSchema(
        base_url="http://localhost:8001/lemmy",
        credentials={"auth_token": "valid_mock_jwt_token"}
    )

    # 1. Validate
    val = await connector.validate(rendition, dest, conn)
    assert val.ok is True

    # 2. Publish
    pub = await connector.publish(rendition, dest, conn, "idem_lemmy_1")
    assert pub.platform_post_id != ""
    assert "/post/" in pub.live_url

    # 3. Get Status
    status = await connector.get_status(pub.platform_post_id, conn)
    assert status.status == "published"

    # 4. Delete
    del_res = await connector.delete(pub.platform_post_id, conn)
    assert del_res.deleted is True


@pytest.mark.asyncio
async def test_ghost_lifecycle():
    connector = registry.get_connector("ghost")

    rendition = RenditionSchema(
        title="Ghost Article: Engineering Clean Multi-Destination Distribution",
        body="A complete technical guide on decoupled connectors, safe retries, and publication certification.",
        tags=["engineering", "distribution"],
        summary="Deep dive into IncuBrix architecture"
    )
    dest = DestinationSchema(
        name="Official Engineering Blog",
        url="http://localhost:8001/ghost",
        platform_key="ghost",
        connector_key="ghost"
    )
    conn = ConnectionSchema(
        base_url="http://localhost:8001/ghost",
        credentials={"admin_api_key": "64f1a2b3c4d5e6f7a8b9c0d1:e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1"}
    )

    # 1. Validate
    val = await connector.validate(rendition, dest, conn)
    assert val.ok is True

    # 2. Publish
    pub = await connector.publish(rendition, dest, conn, "idem_ghost_1")
    assert pub.platform_post_id.startswith("ghost_")
    assert pub.status == "published"

    # 3. Get Status
    status = await connector.get_status(pub.platform_post_id, conn)
    assert status.status == "published"

    # 4. Delete
    del_res = await connector.delete(pub.platform_post_id, conn)
    assert del_res.deleted is True


@pytest.mark.asyncio
async def test_signed_webhook_lifecycle():
    connector = registry.get_connector("signed_webhook")

    rendition = RenditionSchema(
        title="Webhook Broadcast",
        body="Payload dispatched to partner webhook with HMAC-SHA256 signature verification.",
        tags=["webhook", "partner"]
    )
    dest = DestinationSchema(
        name="Partner Syndication Webhook",
        url="http://localhost:8001/webhook",
        platform_key="signed_webhook",
        connector_key="signed_webhook",
        instance_config={"endpoint_url": "http://localhost:8001/webhook"}
    )
    conn = ConnectionSchema(
        base_url="http://localhost:8001/webhook",
        credentials={"hmac_secret": "my_super_secret_webhook_key_12345"}
    )

    # 1. HMAC utility tests
    secret = "my_super_secret_webhook_key_12345"
    payload = b'{"hello": "world"}'
    ts = "1700000000"
    sig = compute_hmac_signature(secret, payload, ts)
    assert sig.startswith("sha256=")
    assert verify_hmac_signature(secret, payload, ts, sig) is True
    assert verify_hmac_signature(secret, payload, ts, "sha256=invalid") is False

    # 2. Validate
    val = await connector.validate(rendition, dest, conn)
    assert val.ok is True

    # 3. Publish
    pub = await connector.publish(rendition, dest, conn, "idem_wh_1")
    assert pub.platform_post_id.startswith("wh_")
    assert pub.status == "published"

    # 4. Get Status
    st = await connector.get_status(pub.platform_post_id, conn)
    assert st.status == "published"

    # 5. Delete
    deleted = await connector.delete(pub.platform_post_id, conn)
    assert deleted.deleted is True


@pytest.mark.asyncio
async def test_simulated_errors_taxonomy():
    connector = registry.get_connector("devto")
    rendition = RenditionSchema(title="Valid Post Title", body="Valid content body with enough characters for devto.")
    dest = DestinationSchema(name="Devto", url="http://localhost:8001/devto", platform_key="devto", connector_key="devto")

    # 401 Simulated Auth Expiry
    conn_bad_auth = ConnectionSchema(base_url="http://localhost:8001/devto", credentials={"api_key": "any"}, metadata={"simulate": "401"})
    with pytest.raises(ConnectorException) as exc_info:
        await connector.publish(rendition, dest, conn_bad_auth, "idem_err_1")
    assert exc_info.value.code == ErrorCode.CONNECTION_AUTH_EXPIRED
    assert exc_info.value.retryable is False

    # 429 Simulated Rate Limit
    conn_429 = ConnectionSchema(base_url="http://localhost:8001/devto", credentials={"api_key": "any"}, metadata={"simulate": "429"})
    with pytest.raises(ConnectorException) as exc_429:
        await connector.publish(rendition, dest, conn_429, "idem_err_2")
    assert exc_429.value.code == ErrorCode.PLATFORM_RATE_LIMIT
    assert exc_429.value.retryable is True
    assert exc_429.value.details.get("retry_after") == 2

    # 422 Simulated Content Rejected
    conn_422 = ConnectionSchema(base_url="http://localhost:8001/devto", credentials={"api_key": "any"}, metadata={"simulate": "422"})
    with pytest.raises(ConnectorException) as exc_422:
        await connector.publish(rendition, dest, conn_422, "idem_err_3")
    assert exc_422.value.code == ErrorCode.PLATFORM_CONTENT_REJECTED
    assert exc_422.value.retryable is False

    # 503 Simulated Platform Unavailable
    conn_503 = ConnectionSchema(base_url="http://localhost:8001/devto", credentials={"api_key": "any"}, metadata={"simulate": "503"})
    with pytest.raises(ConnectorException) as exc_503:
        await connector.publish(rendition, dest, conn_503, "idem_err_4")
    assert exc_503.value.code == ErrorCode.PLATFORM_UNAVAILABLE
    assert exc_503.value.retryable is True
