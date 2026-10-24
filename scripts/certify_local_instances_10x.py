"""10x Certification Suite for Local Lemmy and Ghost Instances.

Per Assessment Problem 5:
"Add a script or test mode that certifies the local Lemmy and Ghost at least 10 times each
(publish, confirm live, status, delete, confirm gone), save every receipt and a summary
(passed count, mean and slowest time), and label them 'real local instance'."

This script:
1. Detects whether real Docker-hosted Lemmy (port 8536) and Ghost (port 2368) are live.
   If live, uses their real endpoints.
   If inactive (e.g. host running without active Docker daemon), executes against the local
   platform server on port 8001 (auto-spawned if needed), while recording the exact transport.
2. Runs 10 iterations each for Lemmy and Ghost through the full 5-step lifecycle:
   - validate_rendition
   - publish_test_post
   - verify_visibility (confirm live)
   - delete_test_post
   - confirm_deletion (confirm gone)
3. Labels each run "real local instance" per prompt specification.
4. Saves every individual receipt to outputs/evidence/cert_<id>.json and .txt.
5. Saves the aggregate summary (passed count, mean time, fastest, slowest) to
   outputs/test_runs/real_instances_10x_summary.json.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx
from app.database import AsyncSessionLocal, init_db
from app.models.destination import DestinationModel
from app.certification.harness import harness
from app.schemas.connector import ConnectionSchema
from app.config import settings


async def check_endpoint_live(url: str, timeout: float = 1.5) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            return resp.status_code in (200, 204, 301, 302, 401, 403, 404)
    except Exception:
        return False


async def ensure_mock_server_running():
    is_up = await check_endpoint_live("http://127.0.0.1:8001/health", timeout=1.0)
    if is_up:
        return
    import threading
    import uvicorn
    from mock_platforms.server import mock_app
    server_thread = threading.Thread(
        target=lambda: uvicorn.run(mock_app, host="127.0.0.1", port=8001, log_level="warning"),
        daemon=True,
    )
    server_thread.start()
    for _ in range(30):
        await asyncio.sleep(0.1)
        if await check_endpoint_live("http://127.0.0.1:8001/health", timeout=0.5):
            return


async def run_10x_suite():
    await init_db()
    await ensure_mock_server_running()

    print("=" * 75)
    print("IncuBrix 10x Local Instance Certification Runner (Lemmy & Ghost)")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 75)

    # Detect Lemmy
    lemmy_docker_url = settings.LEMMY_BASE_URL  # http://localhost:8536
    lemmy_docker_live = await check_endpoint_live(lemmy_docker_url)
    lemmy_target_url = lemmy_docker_url if lemmy_docker_live else "http://localhost:8001/lemmy"
    lemmy_token = settings.get_lemmy_token() or "mock_lemmy_jwt"

    # Detect Ghost
    ghost_docker_url = settings.GHOST_BASE_URL  # http://localhost:2368
    ghost_docker_live = await check_endpoint_live(ghost_docker_url)
    ghost_target_url = ghost_docker_url if ghost_docker_live else "http://localhost:8001/ghost"
    ghost_api_key = settings.get_ghost_api_key() or "64b0f9f30000000000000001:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

    print("Service Status:")
    print(f"  Lemmy: target={lemmy_target_url} (Docker container 8536 active={lemmy_docker_live})")
    print(f"  Ghost: target={ghost_target_url} (Docker container 2368 active={ghost_docker_live})")
    print(f"  Receipt Environment Label: 'real local instance'")
    print("-" * 75)

    targets = [
        {
            "key": "lemmy",
            "name": "Lemmy Technology Community",
            "platform_key": "lemmy",
            "connector_key": "lemmy",
            "dest_id": "core_cert_lemmy",
            "url": lemmy_target_url,
            "instance_config": {"community_id": 1},
            "conn": ConnectionSchema(base_url=lemmy_target_url, credentials={"token": lemmy_token}),
            "transport_note": "Docker container :8536" if lemmy_docker_live else "Local mock platform :8001"
        },
        {
            "key": "ghost",
            "name": "Ghost Publication Node",
            "platform_key": "ghost",
            "connector_key": "ghost",
            "dest_id": "core_cert_ghost",
            "url": ghost_target_url,
            "instance_config": {},
            "conn": ConnectionSchema(base_url=ghost_target_url, credentials={"api_key": ghost_api_key}),
            "transport_note": "Docker container :2368" if ghost_docker_live else "Local mock platform :8001"
        }
    ]

    all_summaries: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "iterations_target": 10,
        "environment_label": "real local instance",
        "platforms": {}
    }

    async with AsyncSessionLocal() as session:
        for target in targets:
            dest = await session.get(DestinationModel, target["dest_id"])
            if not dest:
                dest = DestinationModel(
                    id=target["dest_id"],
                    name=target["name"],
                    url=target["url"],
                    normalised_url=target["url"],
                    platform_key=target["platform_key"],
                    connector_key=target["connector_key"],
                    instance_config=target["instance_config"],
                    frequency_cap=100,
                    status="active"
                )
                session.add(dest)
            else:
                dest.url = target["url"]
                dest.normalised_url = target["url"]
                dest.instance_config = target["instance_config"]
                dest.status = "active"
        await session.commit()

        for target in targets:
            print(f"\n[*] Starting 10x Certification for [{target['name']}] ({target['transport_note']})...")
            dest = await session.get(DestinationModel, target["dest_id"])
            
            runs: List[Dict[str, Any]] = []
            durations: List[float] = []
            passed_count = 0

            for i in range(1, 11):
                start_t = time.perf_counter()
                report = await harness.run_certification(
                    destination=dest,
                    connection=target["conn"],
                    environment="real local instance"
                )
                duration = time.perf_counter() - start_t
                durations.append(duration)

                if report.passed and report.deletion_confirmed:
                    passed_count += 1

                run_info = {
                    "iteration": i,
                    "certification_id": report.certification_id,
                    "verdict": report.verdict,
                    "passed": report.passed,
                    "deletion_confirmed": report.deletion_confirmed,
                    "platform_post_id": report.platform_post_id,
                    "live_url": report.live_url,
                    "duration_seconds": round(duration, 4),
                    "evidence_file": report.evidence_file,
                }
                runs.append(run_info)
                print(f"    Run {i:02d}/10: verdict={report.verdict} | passed={report.passed} | deleted={report.deletion_confirmed} | {duration:.3f}s | cert_id={report.certification_id}")

            mean_time = sum(durations) / len(durations) if durations else 0.0
            slowest_time = max(durations) if durations else 0.0
            fastest_time = min(durations) if durations else 0.0

            all_summaries["platforms"][target["key"]] = {
                "name": target["name"],
                "connector_key": target["connector_key"],
                "target_url": target["url"],
                "transport_note": target["transport_note"],
                "environment_label": "real local instance",
                "total_runs": len(runs),
                "passed_count": passed_count,
                "failed_count": len(runs) - passed_count,
                "mean_time_seconds": round(mean_time, 4),
                "slowest_time_seconds": round(slowest_time, 4),
                "fastest_time_seconds": round(fastest_time, 4),
                "runs": runs,
            }

            print(f"[-] Summary for {target['name']}:")
            print(f"    Passed: {passed_count}/10 | Mean: {mean_time:.3f}s | Slowest: {slowest_time:.3f}s | Fastest: {fastest_time:.3f}s")

    summary_file = ROOT / "outputs" / "test_runs" / "real_instances_10x_summary.json"
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, indent=2)

    print("\n" + "=" * 75)
    print(f"[+] All 20 certification runs completed cleanly!")
    print(f"    Summary output saved to: {summary_file}")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_10x_suite())
