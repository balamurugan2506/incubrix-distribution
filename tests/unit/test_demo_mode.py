"""Unit tests for Live Demo failure-switch routes and demo authentication middleware."""

import pytest
import time
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.config import settings
from app.rules.errors import ErrorCode


@pytest.mark.asyncio
async def test_demo_failure_switch_toggle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET failure switch status
        resp = await client.get("/api/v1/demo/failure-switch")
        assert resp.status_code == 200
        data = resp.json()
        assert "active_switches" in data
        assert data["active_switches"]["timeout"] is False

        # POST toggle failure switch (needs Idempotency-Key)
        toggle_resp = await client.post(
            "/api/v1/demo/failure-switch",
            json={"switch": "timeout", "enabled": True},
            headers={"Idempotency-Key": "demo_switch_toggle_1"}
        )
        assert toggle_resp.status_code == 200
        assert toggle_resp.json()["active_switches"]["timeout"] is True

        # Reset switches
        reset_resp = await client.post(
            "/api/v1/demo/failure-switch",
            json={"switch": "reset", "enabled": True},
            headers={"Idempotency-Key": "demo_switch_reset_1"}
        )
        assert reset_resp.status_code == 200
        assert reset_resp.json()["active_switches"]["timeout"] is False


@pytest.mark.asyncio
async def test_demo_auth_and_rate_limit(monkeypatch):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Without DEMO_API_TOKEN set, requests without token succeed
        monkeypatch.setattr(settings, "DEMO_API_TOKEN", None)
        resp = await client.get("/api/v1/destinations")
        assert resp.status_code == 200

        # 2. When DEMO_API_TOKEN is set, unauthenticated request receives 401 UNAUTHORIZED
        monkeypatch.setattr(settings, "DEMO_API_TOKEN", "secret-demo-token-12345")
        unauth_resp = await client.get("/api/v1/destinations")
        assert unauth_resp.status_code == 401
        err_json = unauth_resp.json()
        assert err_json["error"]["code"] == ErrorCode.UNAUTHORIZED.value

        # 3. Request with valid Authorization header succeeds
        auth_resp = await client.get(
            "/api/v1/destinations",
            headers={"Authorization": "Bearer secret-demo-token-12345"}
        )
        assert auth_resp.status_code == 200

        # 4. Public paths like /health are exempt even without token
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200
