"""Unit tests verifying the exact connector contract and return shapes."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.rules.errors import ErrorCode


@pytest.mark.asyncio
async def test_health_and_ready_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

        resp2 = await client.get("/ready")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["status"] == "ready"
        assert data2["connectors_loaded"] >= 6


@pytest.mark.asyncio
async def test_devto_validate_contract():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Valid rendition
        payload = {
            "rendition": {
                "title": "Validating Distribution in IncuBrix",
                "body": "This is a comprehensive article about multichannel distribution architecture with plenty of details.",
                "tags": ["tech", "distribution"]
            },
            "destination": {
                "name": "Dev.to Community",
                "url": "https://dev.to",
                "platform_key": "devto",
                "connector_key": "devto"
            },
            "connection": {
                "credentials": {"api_key": "dummy_key"}
            }
        }
        resp = await client.post("/connector/v1/devto/validate", json=payload)
        assert resp.status_code == 200
        result = resp.json()
        assert result["ok"] is True
        assert result["violations"] == []

        # Invalid rendition (too short)
        payload["rendition"]["title"] = "Abc"
        payload["rendition"]["body"] = "Short"
        payload["rendition"]["tags"] = ["1", "2", "3", "4", "5", "6"]
        resp_invalid = await client.post("/connector/v1/devto/validate", json=payload)
        assert resp_invalid.status_code == 200
        res_invalid = resp_invalid.json()
        assert res_invalid["ok"] is False
        assert len(res_invalid["violations"]) >= 2


@pytest.mark.asyncio
async def test_assisted_connector_contract():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "rendition": {
                "title": "Manual Submission Test",
                "body": "Content to be posted manually to a strictly moderated community.",
                "summary": "Quick summary",
                "tags": ["incubrix", "launch"],
                "media_urls": ["https://assets.incubrix.test/image1.png"],
                "is_ai_generated": True,
                "ai_disclosure_text": "Drafted with AI assistance, verified by human editor."
            },
            "destination": {
                "name": "Private Moderated Substack",
                "url": "https://moderated.example.com",
                "platform_key": "assisted",
                "connector_key": "assisted",
                "instance_config": {
                    "submission_url": "https://moderated.example.com/submit"
                }
            }
        }

        # build_assist_pack
        resp = await client.post("/connector/v1/assisted/build_assist_pack", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data
        assert "caption" in data
        assert "deep_link" in data
        assert "checklist" in data
        assert len(data["files"]) == 1
        assert "https://moderated.example.com/submit" in data["deep_link"]
        assert len(data["checklist"]) >= 5
        assert "AI Disclosure" in data["caption"]

        # publish must be blocked
        pub_payload = {
            **payload,
            "connection": {"credentials": {}},
            "idempotency_key": "idem_assisted_123"
        }
        resp_pub = await client.post("/connector/v1/assisted/publish", json=pub_payload)
        assert resp_pub.status_code == 400
        err = resp_pub.json()
        assert err["code"] == ErrorCode.CONNECTOR_DISABLED.value
        assert "not permitted" in err["message"].lower()
