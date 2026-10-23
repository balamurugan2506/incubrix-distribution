#!/usr/bin/env python3
"""
Standalone HTTP Batch Runner (Integration 10).
Calls the running IncuBrix API over HTTP (POST /api/v1/...) for a folder, JSON list, or JSONL of inputs.
Does NOT import the app or intercept HTTP in-process.
Default Idempotency-Key = file name + hash of the content.
Writes every result to an output folder with an execution manifest summary.
"""

import os
import sys
import json
import time
import uuid
import hashlib
import argparse
import platform
from datetime import datetime, timezone
from typing import Dict, Any, List
import httpx


def compute_idempotency_key(source_name: str, payload_bytes: bytes) -> str:
    """Compute default idempotency key = file name plus SHA-256 hash of content."""
    content_hash = hashlib.sha256(payload_bytes).hexdigest()[:16]
    clean_name = os.path.basename(source_name).replace(".", "_").replace(" ", "_")
    return f"{clean_name}_{content_hash}"


def load_input_items(input_path: str) -> List[Dict[str, Any]]:
    """Load items from a folder of JSON files, a JSON list/object, or a JSONL file."""
    items = []
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input path not found: {input_path}")

    if os.path.isdir(input_path):
        for fname in sorted(os.listdir(input_path)):
            if fname.endswith(".json"):
                fpath = os.path.join(input_path, fname)
                with open(fpath, "rb") as f:
                    content = f.read()
                    data = json.loads(content.decode("utf-8"))
                    items.append({
                        "source": fname,
                        "raw_bytes": content,
                        "data": data
                    })
    elif input_path.endswith(".jsonl"):
        with open(input_path, "rb") as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line.decode("utf-8"))
                items.append({
                    "source": f"{os.path.basename(input_path)}:line_{idx+1}",
                    "raw_bytes": line,
                    "data": data
                })
    elif input_path.endswith(".json"):
        with open(input_path, "rb") as f:
            content = f.read()
            data = json.loads(content.decode("utf-8"))
            if isinstance(data, list):
                for idx, item in enumerate(data):
                    item_bytes = json.dumps(item, sort_keys=True).encode("utf-8")
                    items.append({
                        "source": f"{os.path.basename(input_path)}:item_{idx+1}",
                        "raw_bytes": item_bytes,
                        "data": item
                    })
            elif isinstance(data, dict):
                items.append({
                    "source": os.path.basename(input_path),
                    "raw_bytes": content,
                    "data": data
                })
    else:
        raise ValueError(f"Unsupported file format: {input_path}. Expected directory, .json, or .jsonl")

    return items


def run_batch_client(
    api_url: str,
    input_path: str,
    output_dir: str,
    timeout_s: float = 30.0,
    api_token: str = None,
    client: httpx.Client = None
) -> Dict[str, Any]:
    """Execute batch runner by making real HTTP calls to the running API server."""
    os.makedirs(output_dir, exist_ok=True)
    items = load_input_items(input_path)
    run_id = f"batch_{uuid.uuid4().hex[:10]}"
    started_at = datetime.now(timezone.utc).isoformat()
    start_time = time.time()

    print(f"==================================================")
    print(f"  IncuBrix HTTP Batch Runner [Run ID: {run_id}]")
    print(f"  Target API: {api_url}")
    print(f"  Loaded Items: {len(items)}")
    print(f"  Output Directory: {output_dir}")
    print(f"==================================================\n")

    results: List[Dict[str, Any]] = []
    warnings: List[str] = []

    client_headers = {
        "User-Agent": f"IncuBrix-BatchRunner/1.0.0 (Python {platform.python_version()})"
    }
    if api_token:
        client_headers["Authorization"] = f"Bearer {api_token}"

    http_client = client or httpx.Client(base_url=api_url, timeout=timeout_s, headers=client_headers)
    should_close_client = client is None

    try:
        # Check API health first
        try:
            health_resp = http_client.get("/health")
            if health_resp.status_code != 200:
                raise RuntimeError(f"API health check failed with status {health_resp.status_code}")
        except Exception as exc:
            raise RuntimeError(f"Cannot connect to API at {api_url}: {exc}") from exc

        for idx, item in enumerate(items, 1):
            source = item["source"]
            payload = item["data"]
            idempotency_key = payload.get("idempotency_key") or compute_idempotency_key(source, item["raw_bytes"])
            correlation_id = f"corr-batch-{uuid.uuid4().hex[:8]}"

            req_headers = {
                "Idempotency-Key": idempotency_key,
                "X-Correlation-Id": correlation_id,
                "Content-Type": "application/json"
            }

            # Determine route: if payload specifies a target endpoint use it, else default to POST /api/v1/jobs/publish
            target_endpoint = payload.get("endpoint", "/api/v1/jobs/publish")
            clean_payload = {k: v for k, v in payload.items() if k not in ("endpoint", "idempotency_key")}

            print(f"[{idx}/{len(items)}] {source} -> POST {target_endpoint} (key={idempotency_key})...")
            item_start = time.time()

            try:
                resp = http_client.post(target_endpoint, json=clean_payload, headers=req_headers)
                item_duration = round(time.time() - item_start, 4)

                result_record = {
                    "item_index": idx,
                    "source": source,
                    "idempotency_key": idempotency_key,
                    "correlation_id": correlation_id,
                    "endpoint": target_endpoint,
                    "http_status": resp.status_code,
                    "duration_seconds": item_duration
                }

                if resp.status_code in (200, 201):
                    result_record["status"] = "succeeded"
                    result_record["response"] = resp.json()
                    print(f"    -> OK ({resp.status_code}) in {item_duration}s")
                elif resp.status_code == 202:
                    # Async job returned - poll for completion
                    job_data = resp.json()
                    job_id = job_data.get("job_id")
                    result_record["job_id"] = job_id
                    print(f"    -> Job queued (job_id={job_id}). Polling...")

                    job_done = False
                    poll_start = time.time()
                    while not job_done and (time.time() - poll_start) < 60:
                        time.sleep(0.5)
                        poll_resp = http_client.get(f"/api/v1/jobs/{job_id}", headers={"X-Correlation-Id": correlation_id})
                        if poll_resp.status_code == 200:
                            job_status = poll_resp.json()
                            if job_status.get("status") in ("succeeded", "failed"):
                                job_done = True
                                result_record["status"] = job_status.get("status")
                                result_record["response"] = job_status
                                print(f"    -> Job finished with status '{job_status.get('status')}'")
                                break

                    if not job_done:
                        result_record["status"] = "timeout"
                        warnings.append(f"{source}: Polling job {job_id} timed out")
                else:
                    result_record["status"] = "error"
                    try:
                        result_record["response"] = resp.json()
                    except Exception:
                        result_record["response"] = resp.text
                    print(f"    -> ERROR {resp.status_code} in {item_duration}s")
                    warnings.append(f"{source}: HTTP {resp.status_code}")

            except Exception as exc:
                item_duration = round(time.time() - item_start, 4)
                result_record = {
                    "item_index": idx,
                    "source": source,
                    "idempotency_key": idempotency_key,
                    "correlation_id": correlation_id,
                    "status": "failed",
                    "error": str(exc),
                    "duration_seconds": item_duration
                }
                print(f"    -> FAILED: {str(exc)} ({item_duration}s)")
                warnings.append(f"{source}: {str(exc)}")

            results.append(result_record)

            # Write individual result file
            safe_source = source.replace(":", "_").replace("/", "_").replace("\\", "_")
            item_out_path = os.path.join(output_dir, f"result_{idx:03d}_{safe_source}.json")
            with open(item_out_path, "w", encoding="utf-8") as f:
                json.dump(result_record, f, indent=2)

    finally:
        if should_close_client:
            http_client.close()

    total_duration = round(time.time() - start_time, 4)
    completed_at = datetime.now(timezone.utc).isoformat()

    manifest = {
        "manifest_version": "1.0.0",
        "run_id": run_id,
        "service_version": "1.0.0",
        "python_version": platform.python_version(),
        "models_or_providers_used": [],
        "models_explanation": "None - HTTP batch runner executes purely against IncuBrix REST endpoints.",
        "settings": {
            "api_url": api_url,
            "input_path": input_path,
            "output_dir": output_dir,
            "timeout_seconds": timeout_s
        },
        "seed": None,
        "timings": {
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_seconds": total_duration
        },
        "cost_estimate": {
            "currency": "USD",
            "amount": 0.00,
            "details": "Local open-source runtime zero marginal cost"
        },
        "warnings": warnings,
        "licence_and_rights": "Apache-2.0, all rights reserved by IncuBrix",
        "ai_generated": False,
        "summary": {
            "total_items": len(items),
            "succeeded": sum(1 for r in results if r.get("status") == "succeeded"),
            "failed": sum(1 for r in results if r.get("status") in ("failed", "error", "timeout")),
            "duration_seconds": total_duration
        },
        "results": results
    }

    summary_file = os.path.join(output_dir, "summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n==================================================")
    print(f"  Batch run finished in {total_duration}s")
    print(f"  Success: {manifest['summary']['succeeded']}/{manifest['summary']['total_items']}")
    print(f"  Summary saved to: {summary_file}")
    print(f"==================================================")

    return manifest


def main():
    parser = argparse.ArgumentParser(description="IncuBrix HTTP Batch Runner (Integration 10)")
    parser.add_argument("--api-url", default=os.getenv("INCUBRIX_API_URL", "http://localhost:8000"), help="Base URL of running IncuBrix API")
    parser.add_argument("--input", required=True, help="Path to input directory of JSON files, a JSON list, or JSONL")
    parser.add_argument("--output-dir", default="outputs/batch_runs", help="Output directory for results and summary")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP request timeout in seconds")
    parser.add_argument("--api-token", default=os.getenv("INCUBRIX_API_TOKEN"), help="Optional Bearer token")

    args = parser.parse_args()
    try:
        run_batch_client(
            api_url=args.api_url,
            input_path=args.input,
            output_dir=args.output_dir,
            timeout_s=args.timeout,
            api_token=args.api_token
        )
    except Exception as exc:
        print(f"Batch runner error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
