"""Advanced Level 1 Test: Catalogue Import, Normalisation, SSRF Guard, and 1,000-row Benchmark."""

import os
import json
import time
import io
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.catalogue.csv_importer import normalise_url, is_ssrf_risk, import_destinations_from_csv
from app.database import AsyncSessionLocal


from mock_platforms.server import mock_app


def test_url_normalisation_and_tracking_stripping():
    """Verify normalisation strips tracking parameters, www, default ports, and lowercases host."""
    raw = "HTTPS://WWW.Example.COM:443/community/ai-discussions/?utm_source=twitter&utm_medium=social&ref=123&topic=test"
    norm = normalise_url(raw)
    assert norm == "https://example.com/community/ai-discussions?topic=test"

    raw_http = "http://dev.to:80/t/python?fbclid=IwAR2345"
    norm_http = normalise_url(raw_http)
    assert norm_http == "https://dev.to/t/python" or norm_http == "http://dev.to/t/python"
    assert "fbclid" not in norm_http


def test_ssrf_guard():
    """Verify SSRF guard blocks private and link-local addresses."""
    assert is_ssrf_risk("10.0.0.1") is True
    assert is_ssrf_risk("192.168.1.1") is True
    assert is_ssrf_risk("127.0.0.1") is True
    assert is_ssrf_risk("169.254.169.254") is True
    # Public domain should not be flagged as SSRF risk
    assert is_ssrf_risk("example.com") is False


@pytest.mark.asyncio
async def test_1000_row_csv_import_benchmark():
    """
    Generate and import 1,000 rows.
    Must finish in under 5 minutes (300 seconds).
    Saves timing output to outputs/test_runs/csv_1000_benchmark.json.
    """
    os.makedirs("outputs/test_runs", exist_ok=True)
    benchmark_file = "outputs/test_runs/csv_1000_benchmark.json"

    # Generate 1,000 rows with a mix of valid destinations, duplicates, and invalid entries
    csv_lines = [
        "name,url,platform_key,connector_key,surface,category,audience_tags,rules_url,frequency_cap"
    ]

    import uuid
    run_tag = uuid.uuid4().hex[:6]

    for i in range(1, 1001):
        if i % 100 == 0:
            # Duplicate of previous item
            csv_lines.append(f"Dup Community {i-1},http://mock.local/mock/community/{run_tag}_{i-1},discourse,discourse,main,ai,\"ai,tech\",http://mock.local/rules.txt,10")
        elif i % 250 == 0:
            # Invalid entry (missing platform)
            csv_lines.append(f"Invalid Community {i},http://mock.local/mock/community/{run_tag}_{i},,,main,ai,\"ai,tech\",,10")
        else:
            # Valid item
            csv_lines.append(f"Community {i},http://mock.local/mock/community/{run_tag}_{i}?utm_source=bench_{i},discourse,discourse,main,saas,\"ai,saas,video\",http://mock.local/rules.txt,10")

    csv_payload = "\n".join(csv_lines)

    start_time = time.time()
    mock_client = AsyncClient(transport=ASGITransport(app=mock_app), base_url="http://mock.local")

    async with AsyncSessionLocal() as db:
        summary = await import_destinations_from_csv(
            csv_content=csv_payload,
            db=db,
            perform_reachability=True,
            allow_local=True,
            concurrency_limit=50,
            http_client=mock_client
        )

    await mock_client.aclose()
    elapsed_seconds = round(time.time() - start_time, 4)

    # 1,000 rows must import in under 5 minutes (300 seconds)
    assert elapsed_seconds < 300.0, f"Benchmark exceeded 5 minutes: took {elapsed_seconds}s"
    assert summary.total_rows == 1000
    assert summary.imported_count > 900
    assert summary.skipped_duplicates >= 10
    assert summary.errors_count >= 2

    rows_per_second = round(summary.total_rows / elapsed_seconds, 2)

    benchmark_result = {
        "benchmark_name": "CSV 1,000 Row Import Benchmark (Advanced 1)",
        "total_rows": summary.total_rows,
        "imported_count": summary.imported_count,
        "skipped_duplicates": summary.skipped_duplicates,
        "errors_count": summary.errors_count,
        "elapsed_seconds": elapsed_seconds,
        "rows_per_second": rows_per_second,
        "target_max_seconds": 300.0,
        "passed": elapsed_seconds < 300.0,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    with open(benchmark_file, "w", encoding="utf-8") as f:
        json.dump(benchmark_result, f, indent=2)

    print(f"\n==================================================")
    print(f"  CSV Import Benchmark Result:")
    print(f"  Total Rows: {summary.total_rows}")
    print(f"  Imported: {summary.imported_count}")
    print(f"  Duplicates: {summary.skipped_duplicates}")
    print(f"  Errors: {summary.errors_count}")
    print(f"  Elapsed Time: {elapsed_seconds}s ({rows_per_second} rows/s)")
    print(f"  Saved report to: {benchmark_file}")
    print(f"==================================================")
