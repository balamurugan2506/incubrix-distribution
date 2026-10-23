"""Executes the full certification run across all 6 Core connectors.
Saves structured JSON and TXT evidence for each run labeled 'real local instance' or 'mock'.
"""

import asyncio
import os
import sys
import json
import httpx

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from app.database import AsyncSessionLocal, init_db
from app.models.destination import DestinationModel
from app.certification.harness import harness
from app.schemas.connector import ConnectionSchema
from app.config import settings


async def check_service_reachable(url: str, timeout: float = 2.0) -> bool:
    """Check if an HTTP service endpoint is actively reachable."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            return resp.status_code in (200, 204, 301, 302, 401, 403, 404)
    except Exception:
        return False


async def run_full_suite():
    await init_db()
    print("=" * 70)
    print("IncuBrix Core Connector Certification Suite Runner")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)

    # Detect local instance availability
    lemmy_real_url = settings.LEMMY_BASE_URL
    lemmy_is_live = await check_service_reachable(lemmy_real_url)
    lemmy_env = "real local instance" if lemmy_is_live else "mock"

    ghost_real_url = settings.GHOST_BASE_URL
    ghost_is_live = await check_service_reachable(ghost_real_url)
    ghost_env = "real local instance" if ghost_is_live else "mock"

    print(f"Detected environments:")
    print(f"  Lemmy: {lemmy_env} (reachable={lemmy_is_live} at {lemmy_real_url})")
    print(f"  Ghost: {ghost_env} (reachable={ghost_is_live} at {ghost_real_url})")
    print(f"  Discourse: mock (at http://localhost:8001/discourse)")
    print(f"  Dev.to: mock (at http://localhost:8001/devto)")
    print(f"  Signed Webhook: mock (at http://localhost:8001/webhook)")
    print(f"  Assisted: assisted-mode (ready-to-post pack generator)")
    print("-" * 70)

    results = []

    destinations_to_certify = [
        {
            "id": "core_cert_discourse",
            "name": "Discourse Engineering Forum",
            "url": "http://localhost:8001/discourse",
            "platform_key": "discourse",
            "connector_key": "discourse",
            "env": "mock",
            "instance_config": {"category_id": 1},
            "conn": ConnectionSchema(
                base_url="http://localhost:8001/discourse",
                credentials={"api_key": "mock_discourse_key", "api_username": "incubrix_bot"}
            )
        },
        {
            "id": "core_cert_devto",
            "name": "Dev.to Technical Blog Hub",
            "url": "http://localhost:8001/devto",
            "platform_key": "devto",
            "connector_key": "devto",
            "env": "mock",
            "instance_config": {},
            "conn": ConnectionSchema(
                base_url="http://localhost:8001/devto",
                credentials={"api_key": "mock_devto_key"}
            )
        },
        {
            "id": "core_cert_webhook",
            "name": "Distribution Webhook Partner",
            "url": "http://localhost:8001/webhook",
            "platform_key": "webhook",
            "connector_key": "signed_webhook",
            "env": "mock",
            "instance_config": {"endpoint_url": "http://localhost:8001/webhook"},
            "conn": ConnectionSchema(
                base_url="http://localhost:8001/webhook",
                credentials={"secret": "super_secret_webhook_key_32_bytes_long!!"}
            )
        },
        {
            "id": "core_cert_assisted",
            "name": "Substack Manual Publication",
            "url": "https://substack.com/publish",
            "platform_key": "assisted",
            "connector_key": "assisted",
            "env": "mock",
            "instance_config": {"submission_url": "https://substack.com/publish"},
            "conn": ConnectionSchema(base_url="https://substack.com/publish", credentials={})
        },
        {
            "id": "core_cert_lemmy",
            "name": "Lemmy Technology Community",
            "url": lemmy_real_url if lemmy_is_live else "http://localhost:8001/lemmy",
            "platform_key": "lemmy",
            "connector_key": "lemmy",
            "env": lemmy_env,
            "instance_config": {"community_id": 1},
            "conn": ConnectionSchema(
                base_url=lemmy_real_url if lemmy_is_live else "http://localhost:8001/lemmy",
                credentials={"token": settings.get_lemmy_token() or "mock_lemmy_jwt"}
            )
        },
        {
            "id": "core_cert_ghost",
            "name": "Ghost Publication Node",
            "url": ghost_real_url if ghost_is_live else "http://localhost:8001/ghost",
            "platform_key": "ghost",
            "connector_key": "ghost",
            "env": ghost_env,
            "instance_config": {},
            "conn": ConnectionSchema(
                base_url=ghost_real_url if ghost_is_live else "http://localhost:8001/ghost",
                credentials={"api_key": settings.get_ghost_api_key() or "64b0f9f30000000000000001:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}
            )
        }
    ]

    async with AsyncSessionLocal() as session:
        for item in destinations_to_certify:
            dest = await session.get(DestinationModel, item["id"])
            if not dest:
                dest = DestinationModel(
                    id=item["id"],
                    name=item["name"],
                    url=item["url"],
                    normalised_url=item["url"],
                    platform_key=item["platform_key"],
                    connector_key=item["connector_key"],
                    instance_config=item["instance_config"],
                    frequency_cap=10,
                    status="active"
                )
                session.add(dest)
            else:
                dest.url = item["url"]
                dest.normalised_url = item["url"]
                dest.instance_config = item["instance_config"]
                dest.status = "active"
        await session.commit()

        for item in destinations_to_certify:
            dest = await session.get(DestinationModel, item["id"])
            print(f"Running certification for [{item['connector_key']}] on '{item['name']}' ({item['env']})...")
            report = await harness.run_certification(
                destination=dest,
                connection=item["conn"],
                environment=item["env"]
            )
            print(f"  -> Verdict: {report.verdict} | Passed: {report.passed} | Deletion Confirmed: {report.deletion_confirmed}")
            print(f"  -> Evidence: {report.evidence_file}")
            results.append({
                "connector_key": item["connector_key"],
                "destination": item["name"],
                "environment": item["env"],
                "verdict": report.verdict,
                "passed": report.passed,
                "deletion_confirmed": report.deletion_confirmed,
                "evidence_file": report.evidence_file
            })

    summary_file = os.path.join("outputs", "test_runs", "core_certification_summary.json")
    os.makedirs(os.path.dirname(summary_file), exist_ok=True)
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("-" * 70)
    print(f"Certification Suite Completed: {len(results)} connectors evaluated.")
    print(f"Summary written to {summary_file}")


if __name__ == "__main__":
    asyncio.run(run_full_suite())
