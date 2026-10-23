"""Integration tests for certification cleanup, field rename detection, demotion, and verdicts."""

import uuid
import pytest
import httpx
from mock_platforms.server import mock_app
from app.main import app
from app.models.destination import DestinationModel
from app.certification.harness import harness
from app.database import AsyncSessionLocal
from app.rules.engine import rules_engine
from app.schemas.connector import RenditionSchema, DestinationSchema, ConnectionSchema
from app.rules.errors import ConnectorException, ErrorCode


@pytest.fixture(autouse=True)
def mock_httpx_client(monkeypatch):
    """Route outbound httpx.AsyncClient requests to the in-process mock platform FastAPI app."""
    real_async_client = httpx.AsyncClient

    def custom_async_client(*args, **kwargs):
        if "transport" not in kwargs:
            kwargs["transport"] = httpx.ASGITransport(app=mock_app)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", custom_async_client)


@pytest.mark.asyncio
async def test_certification_demotes_on_failure_and_refuses_publish():
    """
    If platform fails certification (e.g. 503 or content rejected),
    destination status is set to 'demoted', and subsequent publish is refused.
    """
    dest_id = f"demote_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as session:
        dest = DestinationModel(
            id=dest_id,
            name="Flaky Forum",
            url="http://localhost:8001/discourse",
            normalised_url=f"http://localhost:8001/discourse/{dest_id}",
            platform_key="discourse",
            connector_key="discourse",
            instance_config={"category_id": 1},
            frequency_cap=10,
            status="active"
        )
        session.add(dest)
        await session.commit()

        # Run certification with simulated 503 error
        conn = ConnectionSchema(
            base_url="http://localhost:8001/discourse",
            credentials={"api_key": "k", "api_username": "u"},
            metadata={"simulate": "503"}
        )

        report = await harness.run_certification(dest, connection=conn, environment="mock")
        assert report.passed is False
        assert report.verdict == "failed"

        # Check DB to verify status was demoted (refresh object from DB)
        dest_reloaded = await session.get(DestinationModel, dest_id)
        await session.refresh(dest_reloaded)
        assert dest_reloaded.status == "demoted"

        # Verify that publish to demoted destination is refused
        rend = RenditionSchema(
            title="Valid Discussion Topic for Testing Demotion Refusal",
            body="This body should be refused because the target destination was demoted.",
            tags=["architecture"]
        )
        with pytest.raises(ConnectorException) as exc_info:
            await rules_engine.check_rules(rend, dest_reloaded, db=session)

        assert exc_info.value.code == ErrorCode.CONNECTOR_DISABLED
        assert "demoted" in exc_info.value.message


@pytest.mark.asyncio
async def test_certification_verdict_inconclusive_on_expired_credentials():
    """Verify verdict is 'inconclusive' on expired credentials, not 'passed' or 'failed'."""
    dest_id = f"inconcl_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as session:
        dest = DestinationModel(
            id=dest_id,
            name="Expired Auth Blog",
            url="http://localhost:8001/devto",
            normalised_url=f"http://localhost:8001/devto/{dest_id}",
            platform_key="devto",
            connector_key="devto",
            frequency_cap=10,
            status="active"
        )
        session.add(dest)
        await session.commit()

        # Simulate 401 unauthorized to trigger auth expired
        conn = ConnectionSchema(
            base_url="http://localhost:8001/devto",
            credentials={"api_key": "expired_token"},
            metadata={"simulate": "401"}
        )

        report = await harness.run_certification(dest, connection=conn, environment="mock")
        assert report.passed is False
        assert report.verdict == "inconclusive"
        # Destination is not demoted for temporary auth issues
        dest_reloaded = await session.get(DestinationModel, dest_id)
        await session.refresh(dest_reloaded)
        assert dest_reloaded.status == "active"


@pytest.mark.asyncio
async def test_full_certification_lifecycle_against_all_mock_connectors():
    """
    Test full certification run (publish, verify, delete, confirm gone)
    across Discourse, Dev.to, and Signed Webhook on mock servers.
    """
    # 1. Discourse
    async with AsyncSessionLocal() as session:
        disc_id = f"cert_disc_{uuid.uuid4().hex[:8]}"
        dest_disc = DestinationModel(
            id=disc_id,
            name="Discourse Certification Community",
            url="http://localhost:8001/discourse",
            normalised_url=f"http://localhost:8001/discourse/{disc_id}",
            platform_key="discourse",
            connector_key="discourse",
            instance_config={"category_id": 1}
        )
        session.add(dest_disc)
        await session.commit()

        conn_disc = ConnectionSchema(
            base_url="http://localhost:8001/discourse",
            credentials={"api_key": "test_key", "api_username": "bot"}
        )
        rep_disc = await harness.run_certification(dest_disc, connection=conn_disc, environment="mock")
        assert rep_disc.passed is True
        assert rep_disc.verdict == "passed"
        assert rep_disc.deletion_confirmed is True
        assert rep_disc.environment == "mock"

        # 2. Dev.to
        devto_id = f"cert_devto_{uuid.uuid4().hex[:8]}"
        dest_devto = DestinationModel(
            id=devto_id,
            name="Dev.to Certification Hub",
            url="http://localhost:8001/devto",
            normalised_url=f"http://localhost:8001/devto/{devto_id}",
            platform_key="devto",
            connector_key="devto"
        )
        session.add(dest_devto)
        await session.commit()

        conn_devto = ConnectionSchema(
            base_url="http://localhost:8001/devto",
            credentials={"api_key": "test_devto_key"}
        )
        rep_devto = await harness.run_certification(dest_devto, connection=conn_devto, environment="mock")
        assert rep_devto.passed is True
        assert rep_devto.verdict == "passed"
        assert rep_devto.deletion_confirmed is True

        # 3. Signed Webhook
        wh_id = f"cert_wh_{uuid.uuid4().hex[:8]}"
        dest_wh = DestinationModel(
            id=wh_id,
            name="Signed Webhook Partner",
            url="http://localhost:8001/webhook",
            normalised_url=f"http://localhost:8001/webhook/{wh_id}",
            platform_key="webhook",
            connector_key="signed_webhook",
            instance_config={"endpoint_url": "http://localhost:8001/webhook"}
        )
        session.add(dest_wh)
        await session.commit()

        conn_wh = ConnectionSchema(
            base_url="http://localhost:8001/webhook",
            credentials={"secret": "super_secret_webhook_key_32_bytes_long!!"}
        )
        rep_wh = await harness.run_certification(dest_wh, connection=conn_wh, environment="mock")
        assert rep_wh.passed is True
        assert rep_wh.verdict == "passed"
        assert rep_wh.deletion_confirmed is True
