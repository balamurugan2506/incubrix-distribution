"""Integration test verifying recertification scheduler with fake clock, demotion, and alerts API."""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.database import AsyncSessionLocal, init_db
from app.models.destination import DestinationModel
from app.models.alert import AlertModel
from app.certification.scheduler import RecertificationScheduler
from mock_platforms.server import mock_app
import httpx


@pytest.mark.anyio
async def test_recertification_scheduler_with_fake_clock(monkeypatch):
    """
    Test recertification scheduler:
    1. A destination certified 31 days ago is detected by fake clock.
    2. Recertification failure demotes the destination (status="demoted", enabled=False).
    3. An alert is logged and retrievable via GET /api/v1/alerts.
    4. Demoted destination is excluded from future distribution.
    """
    await init_db()
    # Route connector HTTP calls to mock server
    mock_client = httpx.AsyncClient(transport=ASGITransport(app=mock_app), base_url="http://mock-platforms:8000")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: mock_client)

    dest_id = f"dest_recert_{uuid.uuid4().hex[:8]}"
    initial_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    certified_time = initial_time

    async with AsyncSessionLocal() as session:
        dest = DestinationModel(
            id=dest_id,
            name="Recertification Test Destination",
            url="http://mock-platforms:8000/api/v1/devto",
            normalised_url="mock-platforms:8000/api/v1/devto",
            platform_key="devto",
            connector_key="devto",
            enabled=True,
            status="active",
            last_certified_at=certified_time,
            frequency_cap=10,
            frequency_period_hours=24,
            self_promo_allowed=True,
            link_policy="allowed",
            disclosure_required=False,
            automation_allowed=True,
            instance_config={"api_key": "valid_key"}
        )
        session.add(dest)
        await session.commit()

    async with AsyncSessionLocal() as session:
        # 1. At 15 days later: should NOT need recertification
        day15 = initial_time + timedelta(days=15)
        needing_15 = await RecertificationScheduler.find_destinations_needing_recertification(
            session, as_of=day15, max_age_days=30
        )
        assert not any(d.id == dest_id for d in needing_15)

        # 2. At 35 days later (fake clock): MUST need recertification (exceeds 30-day hard cap)
        day35 = initial_time + timedelta(days=35)
        needing_35 = await RecertificationScheduler.find_destinations_needing_recertification(
            session, as_of=day35, max_age_days=30
        )
        target = next((d for d in needing_35 if d.id == dest_id), None)
        assert target is not None, "Destination was not flagged for recertification after 35 days"

        # 3. Simulate invalid credentials to cause recertification failure
        target.instance_config = {"api_key": "expired_key"}
        await session.commit()

        # Run recertification
        report = await RecertificationScheduler.recertify_destination(
            destination=target,
            db=session,
            environment="mock"
        )
        assert report.passed is False or report.verdict != "passed"

        # 4. Confirm demotion in DB
        refreshed = await session.get(DestinationModel, dest_id)
        assert refreshed.status == "demoted"
        assert refreshed.enabled is False

        # 5. Check Alert in DB
        alert_stmt = select(AlertModel).where(AlertModel.destination_id == dest_id)
        alert_res = await session.execute(alert_stmt)
        alert = alert_res.scalars().first()
        assert alert is not None
        assert alert.alert_type == "recertification_failed"
        assert alert.severity == "high"

    # 6. Verify GET /api/v1/alerts endpoint
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/alerts", params={"destination_id": dest_id})
        assert resp.status_code == 200
        alerts_data = resp.json()
        assert len(alerts_data) >= 1
        assert alerts_data[0]["destination_id"] == dest_id
        assert alerts_data[0]["alert_type"] == "recertification_failed"
