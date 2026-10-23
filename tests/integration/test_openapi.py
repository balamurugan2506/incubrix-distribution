"""Test verifying that openapi.yaml exactly matches the running application schema and routing rules."""

import os
import yaml
import pytest
from app.main import app


def test_openapi_yaml_matches_running_app():
    """Fail if openapi.yaml is stale or does not match app.openapi() exactly."""
    openapi_file = "openapi.yaml"
    assert os.path.exists(openapi_file), "openapi.yaml does not exist"

    with open(openapi_file, "r", encoding="utf-8") as f:
        saved_spec = yaml.safe_load(f)

    app_spec = app.openapi()
    app_spec["openapi"] = "3.1.0"

    # Verify version is OpenAPI 3.1
    assert saved_spec.get("openapi") == "3.1.0"
    assert app_spec.get("openapi") == "3.1.0"

    # Verify all paths and operations match
    assert saved_spec.get("paths", {}).keys() == app_spec.get("paths", {}).keys(), (
        f"Path mismatch between openapi.yaml and app.openapi(): "
        f"{set(saved_spec.get('paths', {}).keys()) ^ set(app_spec.get('paths', {}).keys())}"
    )

    for path, path_item in app_spec.get("paths", {}).items():
        saved_path_item = saved_spec["paths"].get(path, {})
        assert set(saved_path_item.keys()) == set(path_item.keys()), (
            f"Operation mismatch for path '{path}': {set(saved_path_item.keys()) ^ set(path_item.keys())}"
        )


def test_all_routes_under_api_v1_except_allowed_prefixes():
    """
    Integration Standard 2: All routes are under /api/v1/ except:
    /health, /ready, /docs, /redoc, /openapi.json, and /connector/v1/...
    """
    allowed_exceptions = {
        "/health",
        "/ready",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/openapi.json"
    }

    for route in app.routes:
        path = getattr(route, "path", None)
        if not path:
            continue

        if path in allowed_exceptions:
            continue

        if path.startswith("/connector/v1/"):
            continue

        assert path.startswith("/api/v1/"), (
            f"Route '{path}' violates Integration Standard 2 (must be under /api/v1/)"
        )
