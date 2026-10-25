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


def test_settings_cors_origins():
    s = Settings()
    assert "https://incubrix-distribution-network.onrender.com" in s.CORS_ORIGINS
    assert "http://localhost:8000" in s.CORS_ORIGINS
    assert "*" not in s.CORS_ORIGINS

    # Comma-separated string parsing
    s_comma = Settings(CORS_ORIGINS="https://site1.example.com, https://site2.example.com")
    assert s_comma.CORS_ORIGINS == ["https://site1.example.com", "https://site2.example.com"]
