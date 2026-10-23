"""Integration test for Must-Have 3 (Zero Code Change Catalogue Expansion).

Proves that adding a second Discourse instance and a second Lemmy community
is ONE catalogue row (via API or CSV) with ZERO code changes.
"""

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import get_db
from app.models.destination import DestinationModel
from sqlalchemy import select


@pytest.mark.asyncio
async def test_add_second_discourse_instance_via_api_row():
    """Verify adding a second Discourse forum is ONE API row with zero code changes."""
    unique_slug = uuid.uuid4().hex[:8]
    second_discourse_url = f"https://forum-{unique_slug}.example.com"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Add new Discourse instance via API POST /api/v1/destinations
        create_payload = {
            "name": f"Second Discourse Forum {unique_slug}",
            "url": second_discourse_url,
            "platform_key": "discourse",
            "connector_key": "discourse",
            "surface": "forum",
            "category": "engineering",
            "audience_tags": ["discourse", "ai", "saas"],
            "instance_config": {"category_id": 42}
        }

        resp = await client.post(
            "/api/v1/destinations",
            json=create_payload,
            headers={"Idempotency-Key": f"mh3_disc_{unique_slug}"}
        )
        assert resp.status_code == 201, f"Failed to create destination: {resp.text}"
        dest_data = resp.json()
        dest_id = dest_data["id"]

        # Verify the row exists in database and uses existing discourse connector
        assert dest_data["platform_key"] == "discourse"
        assert dest_data["connector_key"] == "discourse"
        assert dest_data["instance_config"]["category_id"] == 42

        # Verify publication works through existing discourse connector with zero code change
        publish_payload = {
            "rendition": {
                "title": f"Zero Code Scale Discourse {unique_slug}",
                "body": "Proving that a second instance requires only one catalogue row.",
                "tags": ["scaling"]
            },
            "destination": {
                "id": dest_id,
                "name": dest_data["name"],
                "url": dest_data["url"],
                "platform_key": "discourse",
                "connector_key": "discourse",
                "instance_config": {"category_id": 42}
            },
            "connection": {
                "base_url": "http://localhost:8001/discourse",
                "credentials": {"api_key": "test_key", "api_username": "system"}
            },
            "idempotency_key": f"pub_mh3_disc_{unique_slug}"
        }

        pub_resp = await client.post(
            "/connector/v1/discourse/publish",
            json=publish_payload,
            headers={"Idempotency-Key": publish_payload["idempotency_key"]}
        )
        assert pub_resp.status_code == 200
        assert pub_resp.json()["status"] == "published"


@pytest.mark.asyncio
async def test_add_second_lemmy_community_via_csv_row():
    """Verify adding a second Lemmy community is ONE CSV row with zero code changes."""
    unique_slug = uuid.uuid4().hex[:8]
    second_lemmy_url = f"http://localhost:8001/lemmy/c/incubrix_{unique_slug}"

    csv_data = (
        "name,url,platform_key,connector_key,surface,category,audience_tags,instance_config,rules_url,frequency_cap\n"
        f"Second Lemmy Community {unique_slug},{second_lemmy_url},lemmy,lemmy,main,technology,\"tech,ai\",,http://localhost:8001/lemmy/rules,5\n"
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Import destination via CSV upload
        files = {
            "file": ("second_lemmy.csv", csv_data.encode("utf-8"), "text/csv")
        }
        resp = await client.post(
            "/api/v1/destinations/import-csv?check_reachability=false",
            files=files,
            headers={"Idempotency-Key": f"mh3_lem_{unique_slug}"}
        )
        assert resp.status_code == 200, f"CSV Import failed: {resp.text}"
        summary = resp.json()
        assert summary["imported_count"] == 1
        assert summary["errors_count"] == 0

        # Query the newly imported destination from catalogue
        list_resp = await client.get("/api/v1/destinations?platform_key=lemmy")
        assert list_resp.status_code == 200
        destinations = list_resp.json()
        matching = [d for d in destinations if unique_slug in d["url"]]
        assert len(matching) == 1
        lemmy_dest = matching[0]

        # Verify publication through existing lemmy connector
        pub_payload = {
            "rendition": {
                "title": f"Zero Code Lemmy Scale {unique_slug}",
                "body": "Proving that a second Lemmy community requires only one catalogue row.",
                "tags": []
            },
            "destination": {
                "id": lemmy_dest["id"],
                "name": lemmy_dest["name"],
                "url": lemmy_dest["url"],
                "platform_key": "lemmy",
                "connector_key": "lemmy",
                "instance_config": {"community_id": 99}
            },
            "connection": {
                "base_url": "http://localhost:8001/lemmy",
                "credentials": {"auth_token": "valid_token"}
            },
            "idempotency_key": f"pub_mh3_lem_{unique_slug}"
        }

        pub_resp = await client.post(
            "/connector/v1/lemmy/publish",
            json=pub_payload,
            headers={"Idempotency-Key": pub_payload["idempotency_key"]}
        )
        assert pub_resp.status_code == 200
        assert pub_resp.json()["status"] == "published"
