"""Integration test for standalone HTTP batch runner (Integration 10)."""

import os
import json
import tempfile
import pytest
from unittest.mock import patch
import httpx
from app.main import app
from scripts.batch_runner import compute_idempotency_key, load_input_items, run_batch_client


def test_idempotency_key_computation():
    """Verify default idempotency key = file name plus content hash."""
    name = "post_example.json"
    content = b'{"title": "Test Title", "body": "Content"}'
    key = compute_idempotency_key(name, content)
    assert key.startswith("post_example_json_")
    assert len(key.split("_")[-1]) == 16


def test_load_input_items_json_and_jsonl(tmp_path):
    """Verify loading input items from JSON list and JSONL formats."""
    # Test JSON list
    json_path = tmp_path / "inputs.json"
    data = [{"title": "Item 1"}, {"title": "Item 2"}]
    json_path.write_text(json.dumps(data), encoding="utf-8")

    items = load_input_items(str(json_path))
    assert len(items) == 2
    assert items[0]["data"]["title"] == "Item 1"

    # Test JSONL
    jsonl_path = tmp_path / "inputs.jsonl"
    jsonl_content = '{"title": "Line 1"}\n{"title": "Line 2"}\n'
    jsonl_path.write_text(jsonl_content, encoding="utf-8")

    items_l = load_input_items(str(jsonl_path))
    assert len(items_l) == 2
    assert items_l[1]["data"]["title"] == "Line 2"


from fastapi.testclient import TestClient


def test_batch_runner_http_execution(tmp_path):
    """Verify batch runner calls API via HTTP transport, writes outputs and summary manifest."""
    input_file = tmp_path / "test_batch.json"
    batch_data = [
        {
            "endpoint": "/api/v1/destinations",
            "name": "Batch Test Community",
            "url": "https://batch-test.example.com",
            "platform_key": "discourse",
            "connector_key": "discourse",
            "instance_config": {"category_id": 99}
        }
    ]
    input_file.write_text(json.dumps(batch_data), encoding="utf-8")
    out_dir = tmp_path / "out"

    test_client = TestClient(app, base_url="http://testserver")
    manifest = run_batch_client(
        api_url="http://testserver",
        input_path=str(input_file),
        output_dir=str(out_dir),
        client=test_client
    )

    assert manifest["summary"]["total_items"] == 1
    assert manifest["summary"]["succeeded"] == 1
    assert "manifest_version" in manifest
    assert "licence_and_rights" in manifest
    assert "models_or_providers_used" in manifest

    summary_file = out_dir / "summary.json"
    assert summary_file.exists()
    summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
    assert summary_data["summary"]["succeeded"] == 1
