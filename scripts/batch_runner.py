"""CLI Batch Runner for automated test execution and evidence generation."""

import os
import sys
import json
import time
import uuid
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.connectors.registry import registry
from app.schemas.connector import RenditionSchema, DestinationSchema, ConnectionSchema
from app.config import settings
from mock_platforms.server import mock_app
import httpx


async def run_batch():
    output_dir = os.path.join("outputs", "test_runs")
    os.makedirs(output_dir, exist_ok=True)

    run_id = f"batch_{uuid.uuid4().hex[:10]}"
    start_time = time.time()
    started_at = datetime.now(timezone.utc).isoformat()

    print(f"==================================================")
    print(f"  IncuBrix CLI Batch Runner [Run ID: {run_id}]")
    print(f"  Simulation Mode: {settings.SIMULATION_MODE}")
    print(f"==================================================\n")

    # Intercept HTTPX calls and route directly to mock_app in-process
    real_async_client = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.ASGITransport(app=mock_app)
        return real_async_client(*args, **kwargs)

    httpx.AsyncClient = mock_async_client

    test_cases = [
        {
            "connector_key": "devto",
            "name": "Dev.to Technical Article",
            "rendition": {
                "title": "Scaling Distribution Networks in Python 3.12",
                "body": "Comprehensive exploration of pure connector runtimes, idempotency, and asynchronous jobs.",
                "tags": ["python", "architecture", "fastapi"]
            },
            "dest_config": {"organization_id": 101}
        },
        {
            "connector_key": "discourse",
            "name": "Discourse Community Discussion",
            "rendition": {
                "title": "Discussion: Long-Tail Distribution Network Architecture",
                "body": "How do you handle multi-destination syndication with rate limits and safe retries?",
                "tags": ["discussion", "engineering"]
            },
            "dest_config": {"category_id": 4}
        },
        {
            "connector_key": "lemmy",
            "name": "Lemmy Fediverse Post",
            "rendition": {
                "title": "Fediverse Content Syndication Principles",
                "body": "Decentralized posting rules, frequency caps, and idempotency guarantees in IncuBrix.",
                "canonical_url": "https://incubrix.test/articles/fediverse-principles"
            },
            "dest_config": {"community_id": 1}
        },
        {
            "connector_key": "ghost",
            "name": "Ghost Editorial Publication",
            "rendition": {
                "title": "Architecting High-Throughput Long-Tail Distribution",
                "body": "Clean separation of connector contracts from IncuBrix domain models.",
                "tags": ["cloud", "distribution"],
                "summary": "Engineering overview of IncuBrix assessment 4"
            },
            "dest_config": {}
        },
        {
            "connector_key": "signed_webhook",
            "name": "Partner Signed Webhook",
            "rendition": {
                "title": "Webhook Event Distribution Payload",
                "body": "Raw payload sent to partner with HMAC-SHA256 signature in X-IncuBrix-Signature.",
                "tags": ["webhook", "syndication"]
            },
            "dest_config": {"endpoint_url": "http://localhost:8001/webhook"}
        },
        {
            "connector_key": "assisted",
            "name": "Moderated Manual Community",
            "rendition": {
                "title": "Manual Moderation Package",
                "body": "High-value post for human-moderated publication with guidelines and checklist.",
                "summary": "Manual pack",
                "media_urls": ["https://assets.incubrix.test/chart.png"],
                "is_ai_generated": True,
                "ai_disclosure_text": "Drafted with assistance from AI, reviewed by human editor."
            },
            "dest_config": {"submission_url": "https://moderated.example.com/submit"}
        }
    ]

    results: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for idx, tc in enumerate(test_cases, 1):
        c_key = tc["connector_key"]
        print(f"[{idx}/{len(test_cases)}] Executing connector: {c_key} ({tc['name']})...")

        connector = registry.get_connector(c_key)
        rend = RenditionSchema(**tc["rendition"])
        dest = DestinationSchema(
            name=tc["name"],
            url=f"http://localhost:8001/{c_key}",
            platform_key=c_key,
            connector_key=c_key,
            instance_config=tc["dest_config"]
        )
        conn = ConnectionSchema(
            base_url=f"http://localhost:8001/{c_key}",
            credentials={
                "api_key": "valid_test_key",
                "auth_token": "valid_token",
                "api_username": "incubrix_bot",
                "admin_api_key": "64f1a2b3c4d5e6f7a8b9c0d1:e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1",
                "hmac_secret": "batch_secret_123"
            }
        )

        item_start = time.time()
        try:
            # 1. Validate
            val = await connector.validate(rend, dest, conn)

            # 2. Publish or Assist Pack
            if c_key == "assisted":
                assist_pack = await connector.build_assist_pack(rend, dest)
                post_id = "assisted_pack"
                live_url = assist_pack.deep_link
                status_str = "pack_generated"
                del_success = True
            else:
                pub = await connector.publish(rend, dest, conn, f"batch_idem_{idx}")
                post_id = pub.platform_post_id
                live_url = pub.live_url
                status_str = pub.status

                # Verify status
                st = await connector.get_status(post_id, conn)

                # Delete test post (cleanup within 10 min requirement)
                del_res = await connector.delete(post_id, conn)
                del_success = del_res.deleted

            duration = round(time.time() - item_start, 4)
            print(f"    -> Success: status={status_str}, live_url={live_url}, deleted={del_success} ({duration}s)")

            results.append({
                "connector_key": c_key,
                "name": tc["name"],
                "status": "passed",
                "platform_post_id": post_id,
                "live_url": live_url,
                "deletion_confirmed": del_success,
                "duration_seconds": duration
            })

        except Exception as exc:
            duration = round(time.time() - item_start, 4)
            print(f"    -> FAILED: {str(exc)} ({duration}s)")
            results.append({
                "connector_key": c_key,
                "name": tc["name"],
                "status": "failed",
                "error": str(exc),
                "duration_seconds": duration
            })
            warnings.append(f"{c_key}: {str(exc)}")

    total_duration = round(time.time() - start_time, 4)
    manifest = {
        "run_id": run_id,
        "app_name": "IncuBrix Distribution Network",
        "app_version": "1.0.0",
        "openapi_version": "3.1.0",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "total_duration_seconds": total_duration,
        "configuration": {
            "simulation_mode": settings.SIMULATION_MODE,
            "database_url": settings.DATABASE_URL,
            "storage_backend": settings.STORAGE_BACKEND
        },
        "licence_information": "Commercial Use Permitted - PSF/MIT/BSD/Apache-2.0 (see SOURCES.md)",
        "estimated_cost_usd": 0.00,
        "summary": {
            "total_test_cases": len(test_cases),
            "passed": sum(1 for r in results if r["status"] == "passed"),
            "failed": sum(1 for r in results if r["status"] == "failed"),
        },
        "results": results,
        "warnings": warnings
    }

    manifest_file = os.path.join(output_dir, f"{run_id}_manifest.json")
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n==================================================")
    print(f"  Batch run completed in {total_duration}s")
    print(f"  Passed: {manifest['summary']['passed']}/{manifest['summary']['total_test_cases']}")
    print(f"  Manifest Output: {manifest_file}")
    print(f"==================================================")
    return manifest_file


if __name__ == "__main__":
    asyncio.run(run_batch())
