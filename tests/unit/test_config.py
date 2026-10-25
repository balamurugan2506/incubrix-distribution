"""Unit tests for configuration loading."""

from app.config import Settings


def test_settings_defaults():
    s = Settings()
    assert s.APP_ENV in ("development", "test", "production")
    assert s.SIMULATION_MODE is True
    assert s.PORT == 8000
    assert s.HOST == "0.0.0.0"
    assert len(s.INCUBRIX_WEBHOOK_SECRET) >= 16


def test_dynamic_shared_credentials_reload(tmp_path):
    creds_file = tmp_path / "creds.json"
    import json
    creds_file.write_text(json.dumps({"lemmy_auth_token": "token_v1", "ghost_admin_api_key": "key_v1"}))

    s = Settings(SHARED_CREDENTIALS_FILE=str(creds_file))
    assert s.get_lemmy_token() == "token_v1"
    assert s.get_ghost_api_key() == "key_v1"

    # Simulate seed script updating the credentials file after service has started
    import time
    time.sleep(0.05)
    creds_file.write_text(json.dumps({"lemmy_auth_token": "token_v2", "ghost_admin_api_key": "key_v2"}))

    # Re-reading should dynamically pick up token_v2
    assert s.get_lemmy_token() == "token_v2"
    assert s.get_ghost_api_key() == "key_v2"


def test_settings_cors_origins_default(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    s = Settings()
    assert isinstance(s.CORS_ORIGINS, list)
    assert "https://incubrix-distribution-network.onrender.com" in s.CORS_ORIGINS
    assert "http://localhost:8000" in s.CORS_ORIGINS
    assert "*" not in s.CORS_ORIGINS


def test_settings_cors_origins_comma_separated_env(monkeypatch):
    # Tests the exact Render environment variable string format
    render_origins = "https://incubrix-distribution-network.onrender.com,http://localhost:8000,http://127.0.0.1:8000"
    monkeypatch.setenv("CORS_ORIGINS", render_origins)
    s = Settings()
    assert isinstance(s.CORS_ORIGINS, list)
    assert s.CORS_ORIGINS == [
        "https://incubrix-distribution-network.onrender.com",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]


def test_settings_cors_origins_json_list_env(monkeypatch):
    # Tests JSON-list format in environment variable
    json_origins = '["https://site1.example.com", "https://site2.example.com"]'
    monkeypatch.setenv("CORS_ORIGINS", json_origins)
    s = Settings()
    assert isinstance(s.CORS_ORIGINS, list)
    assert s.CORS_ORIGINS == ["https://site1.example.com", "https://site2.example.com"]


def test_settings_cors_origins_direct_kwargs():
    # Comma-separated string parsing via kwargs
    s_comma = Settings(CORS_ORIGINS="https://site1.example.com, https://site2.example.com")
    assert s_comma.CORS_ORIGINS == ["https://site1.example.com", "https://site2.example.com"]

    # JSON-list string parsing via kwargs
    s_json = Settings(CORS_ORIGINS='["https://json1.example.com", "https://json2.example.com"]')
    assert s_json.CORS_ORIGINS == ["https://json1.example.com", "https://json2.example.com"]

    # Direct list via kwargs
    s_list = Settings(CORS_ORIGINS=["https://direct.example.com"])
    assert s_list.CORS_ORIGINS == ["https://direct.example.com"]


def test_settings_cors_origins_wildcard_rejected(monkeypatch):
    import pytest
    from pydantic import ValidationError

    # Wildcard in kwargs raises ValidationError
    with pytest.raises(ValidationError):
        Settings(CORS_ORIGINS="*")

    with pytest.raises(ValidationError):
        Settings(CORS_ORIGINS=["*", "https://allowed.example.com"])

    # Wildcard in environment variable raises ValidationError / SettingsError
    monkeypatch.setenv("CORS_ORIGINS", "https://site.example.com, *")
    with pytest.raises(Exception):
        Settings()


def test_settings_cors_origins_invalid_safe():
    # Empty string normalizes safely to empty list
    s_empty = Settings(CORS_ORIGINS="")
    assert s_empty.CORS_ORIGINS == []

    # Whitespace only string normalizes safely to empty list
    s_whitespace = Settings(CORS_ORIGINS="   ")
    assert s_whitespace.CORS_ORIGINS == []

    # Malformed JSON bracket string falls back safely to comma split without crashing
    s_bad_json = Settings(CORS_ORIGINS="[malformed, json]")
    assert isinstance(s_bad_json.CORS_ORIGINS, list)


