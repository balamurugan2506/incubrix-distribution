"""Regression tests for Swagger UI CORS support, preflight handling, and security preservation."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.config import settings
from app.rules.errors import ErrorCode


DEPLOYED_ORIGIN = "https://incubrix-distribution-network.onrender.com"
LOCAL_ORIGIN = "http://localhost:8000"
UNAUTHORIZED_ORIGIN = "https://attacker.evil.example.com"


@pytest.mark.asyncio
async def test_swagger_origin_get_health_cors_headers():
    """Verify GET /health with deployed Swagger UI Origin returns 200 and required CORS headers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"Origin": DEPLOYED_ORIGIN})
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == DEPLOYED_ORIGIN
        assert response.headers.get("access-control-allow-credentials") == "true"
        data = response.json()
        assert data.get("status") == "healthy"


@pytest.mark.asyncio
async def test_swagger_origin_options_health_preflight():
    """Verify OPTIONS /health preflight succeeds with 200 and allowed methods/headers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": DEPLOYED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "accept",
            }
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == DEPLOYED_ORIGIN
        assert response.headers.get("access-control-allow-credentials") == "true"
        allow_methods = response.headers.get("access-control-allow-methods", "")
        assert "GET" in allow_methods


@pytest.mark.asyncio
async def test_protected_route_options_preflight_succeeds_without_auth(monkeypatch):
    """Verify browser preflight OPTIONS on protected endpoints succeeds even when DEMO_API_TOKEN is active."""
    monkeypatch.setattr(settings, "DEMO_API_TOKEN", "prod-demo-secret-token")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Browser preflight sends no Authorization header
        response = await client.options(
            "/api/v1/destinations",
            headers={
                "Origin": DEPLOYED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,accept",
            }
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == DEPLOYED_ORIGIN


@pytest.mark.asyncio
async def test_security_auth_is_preserved_with_cors(monkeypatch):
    """Ensure DemoAuthAndRateLimitMiddleware is still enforced on actual GET/POST requests."""
    monkeypatch.setattr(settings, "DEMO_API_TOKEN", "prod-demo-secret-token")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request with Origin but WITHOUT token must fail 401
        unauth_resp = await client.get(
            "/api/v1/destinations",
            headers={"Origin": DEPLOYED_ORIGIN}
        )
        assert unauth_resp.status_code == 401
        assert unauth_resp.json()["error"]["code"] == ErrorCode.UNAUTHORIZED.value

        # Request with Origin and WITH valid token must succeed 200 and include CORS header
        auth_resp = await client.get(
            "/api/v1/destinations",
            headers={
                "Origin": DEPLOYED_ORIGIN,
                "Authorization": "Bearer prod-demo-secret-token"
            }
        )
        assert auth_resp.status_code == 200
        assert auth_resp.headers.get("access-control-allow-origin") == DEPLOYED_ORIGIN


@pytest.mark.asyncio
async def test_unauthorized_origin_does_not_receive_cors_headers():
    """Verify origins not in settings.CORS_ORIGINS do not receive access-control-allow-origin."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"Origin": UNAUTHORIZED_ORIGIN})
        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers


def test_cors_policy_no_wildcard_with_credentials():
    """Ensure settings.CORS_ORIGINS never contains wildcard '*' when allow_credentials=True."""
    assert "*" not in settings.CORS_ORIGINS
    assert DEPLOYED_ORIGIN in settings.CORS_ORIGINS
    assert LOCAL_ORIGIN in settings.CORS_ORIGINS
