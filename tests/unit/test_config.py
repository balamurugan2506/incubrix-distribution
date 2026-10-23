"""Unit tests for configuration loading."""

from app.config import Settings


def test_settings_defaults():
    s = Settings()
    assert s.APP_ENV in ("development", "test", "production")
    assert s.SIMULATION_MODE is True
    assert s.PORT == 8000
    assert s.HOST == "0.0.0.0"
    assert "sqlite" in s.DATABASE_URL
    assert len(s.INCUBRIX_WEBHOOK_SECRET) >= 16
