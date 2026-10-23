"""Integration tests for GET /health, GET /ready, and JSON structured logging with Correlation ID."""

import io
import json
import logging
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.logging_conf import JSONFormatter, logger


@pytest.mark.asyncio
async def test_health_endpoint():
    """Verify GET /health returns expected fields and healthy status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        assert "version" in data
        assert "app_env" in data
        assert "simulation_mode" in data


@pytest.mark.asyncio
async def test_ready_endpoint():
    """Verify GET /ready returns expected fields and ready status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ready"
        assert data.get("database") == "connected"
        assert data.get("connectors_loaded", 0) > 0


@pytest.mark.asyncio
async def test_json_logging_with_correlation_id():
    """Verify logs are JSON lines containing timestamp, level, job_id, and correlation_id."""
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setFormatter(JSONFormatter())
    
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    test_correlation_id = f"corr-{uuid.uuid4().hex[:8]}"

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Send request with custom correlation ID
            response = await client.get("/health", headers={"X-Correlation-Id": test_correlation_id})
            assert response.status_code == 200
            assert response.headers.get("X-Correlation-Id") == test_correlation_id

            # Emit a log during this session
            logger.info("Test health access logged")

            handler.flush()
            output = log_capture.getvalue()
            assert output.strip() != "", "Log output should not be empty"

            lines = output.strip().split("\n")
            json_logs = []
            for line in lines:
                try:
                    json_logs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

            assert len(json_logs) > 0, "Expected at least one valid JSON log line"
            
            # Verify keys on each JSON line
            for log_entry in json_logs:
                assert "timestamp" in log_entry
                assert "level" in log_entry
                assert "message" in log_entry
                assert "job_id" in log_entry
                assert "correlation_id" in log_entry

    finally:
        root_logger.removeHandler(handler)
