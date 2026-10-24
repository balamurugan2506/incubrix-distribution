"""Test verifying that tests are 100% self-contained with no external setup required (Integration Standard 1)."""

import pytest
import httpx


@pytest.mark.asyncio
async def test_mock_platform_server_self_contained():
    """Verify that the mock platforms server is automatically running and healthy in the test session."""
    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.get("http://localhost:8001/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"
        assert data.get("service") == "incubrix-mock"
