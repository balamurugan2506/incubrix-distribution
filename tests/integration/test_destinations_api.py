"""Integration tests for Destination Catalogue CRUD and CSV import."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db, async_engine, Base


@pytest.fixture(autouse=True)
async def setup_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.mark.asyncio
async def test_destination_crud_and_duplicates():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create Destination
        payload = {
            "name": "Discourse Tech Community",
            "url": "https://forum.incubrix.test/tech/",
            "platform_key": "discourse",
            "connector_key": "discourse",
            "frequency_cap": 5,
            "self_promo_allowed": False,
            "link_policy": "restricted",
            "instance_config": {"category_id": 4}
        }
        res_create = await client.post(
            "/api/v1/destinations",
            json=payload,
            headers={"Idempotency-Key": "dest_create_key_1"}
        )
        assert res_create.status_code == 201
        created = res_create.json()
        assert created["id"].startswith("dest_")
        assert created["normalised_url"] == "https://forum.incubrix.test/tech"

        # 2. Duplicate Detection (different trailing slash or www)
        dup_payload = {
            **payload,
            "name": "Duplicate Forum",
            "url": "https://www.forum.incubrix.test/tech"
        }
        res_dup = await client.post(
            "/api/v1/destinations",
            json=dup_payload,
            headers={"Idempotency-Key": "dest_create_key_2"}
        )
        assert res_dup.status_code == 409
        assert "already exists" in res_dup.json()["detail"]

        # 3. Get by ID
        dest_id = created["id"]
        res_get = await client.get(f"/api/v1/destinations/{dest_id}")
        assert res_get.status_code == 200
        assert res_get.json()["name"] == "Discourse Tech Community"

        # 4. Update
        res_update = await client.put(f"/api/v1/destinations/{dest_id}", json={"frequency_cap": 8})
        assert res_update.status_code == 200
        assert res_update.json()["frequency_cap"] == 8

        # 5. List
        res_list = await client.get("/api/v1/destinations?platform_key=discourse")
        assert res_list.status_code == 200
        items = res_list.json()
        assert any(d["id"] == dest_id for d in items)

        # 6. Delete
        res_del = await client.delete(f"/api/v1/destinations/{dest_id}")
        assert res_del.status_code == 204

        # Confirm deleted
        res_gone = await client.get(f"/api/v1/destinations/{dest_id}")
        assert res_gone.status_code == 404


@pytest.mark.asyncio
async def test_csv_import_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        csv_data = (
            "name,url,platform_key,connector_key,surface,category,audience_tags,est_audience,frequency_cap\n"
            "Dev Community,https://dev.to,devto,devto,article,tech,\"coding,python\",50000,10\n"
            "Dev Community Dup,https://www.dev.to/,devto,devto,article,tech,\"coding\",50000,10\n"
            "Missing Platform,https://example.com,,,main,general,\"\",0,10\n"
            "Ghost Tech Blog,https://blog.example.com,ghost,ghost,blog,engineering,\"software\",25000,5\n"
        )
        files = {"file": ("destinations.csv", csv_data.encode("utf-8"), "text/csv")}
        res = await client.post("/api/v1/destinations/import-csv?check_reachability=false", files=files)
        assert res.status_code == 200
        summary = res.json()
        print("CSV SUMMARY:", summary)

        assert summary["total_rows"] == 4
        assert summary["imported_count"] == 2
        assert summary["skipped_duplicates"] == 1
        assert summary["errors_count"] == 1
