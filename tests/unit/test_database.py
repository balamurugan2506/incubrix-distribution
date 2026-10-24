"""Unit tests for database initialization, safe directory creation, and URL configuration."""

import pytest
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.config import Settings
from app.database import ensure_db_directory, init_db, Base


@pytest.mark.asyncio
async def test_ensure_db_directory_creates_missing_directory(tmp_path):
    """Test that SQLite parent directories are safely created when they do not exist."""
    nested_dir = tmp_path / "deeply" / "nested" / "db_folder"
    assert not nested_dir.exists()

    db_file = nested_dir / "test_nested.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    parent = ensure_db_directory(db_url)
    assert parent is not None
    assert parent.exists()
    assert parent == nested_dir

    # Verify that async engine can connect and initialize tables cleanly
    engine = create_async_engine(db_url, connect_args={"check_same_thread": False})
    try:
        await init_db(engine=engine)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='destinations'"))
            row = result.fetchone()
            assert row is not None
            assert row[0] == "destinations"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ensure_db_directory_in_memory():
    """Test that in-memory SQLite databases do not attempt directory creation and initialize cleanly."""
    in_memory_urls = [
        "sqlite+aiosqlite:///:memory:",
        "sqlite:///:memory:",
        "sqlite://",
        "sqlite+aiosqlite://"
    ]

    for url in in_memory_urls:
        res = ensure_db_directory(url)
        assert res is None, f"Expected None for in-memory URL {url}, got {res}"

    # Verify table creation on in-memory SQLite
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    try:
        await init_db(engine=engine)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT count(*) FROM destinations"))
            count = result.scalar()
            assert count == 0
    finally:
        await engine.dispose()


def test_ensure_db_directory_relative_path(tmp_path, monkeypatch):
    """Test that relative SQLite file paths correctly create the relative parent directory."""
    monkeypatch.chdir(tmp_path)
    relative_url = "sqlite+aiosqlite:///./sub_relative/incubrix.db"

    assert not (tmp_path / "sub_relative").exists()
    parent = ensure_db_directory(relative_url)

    assert parent is not None
    assert (tmp_path / "sub_relative").exists()


def test_ensure_db_directory_non_sqlite_and_invalid():
    """Test that non-SQLite or invalid URLs safely return None without errors."""
    assert ensure_db_directory("") is None
    assert ensure_db_directory(None) is None
    assert ensure_db_directory("not_a_valid_url") is None
    assert ensure_db_directory("postgresql+asyncpg://user:pass@localhost:5432/dbname") is None


def test_database_url_configuration_and_sync_derivation():
    """Test that DATABASE_URL is configurable and SYNC_DATABASE_URL is automatically kept in sync."""
    # 1. Default configuration
    default_settings = Settings()
    assert default_settings.DATABASE_URL == "sqlite+aiosqlite:///./incubrix.db"
    assert default_settings.SYNC_DATABASE_URL == "sqlite:///./incubrix.db"

    # 2. Configured custom DATABASE_URL derives SYNC_DATABASE_URL
    custom_settings = Settings(DATABASE_URL="sqlite+aiosqlite:////tmp/incubrix.db")
    assert custom_settings.DATABASE_URL == "sqlite+aiosqlite:////tmp/incubrix.db"
    assert custom_settings.SYNC_DATABASE_URL == "sqlite:////tmp/incubrix.db"

    # 3. Explicit SYNC_DATABASE_URL takes precedence if provided
    explicit_settings = Settings(
        DATABASE_URL="sqlite+aiosqlite:////tmp/incubrix.db",
        SYNC_DATABASE_URL="sqlite:///custom_explicit.db"
    )
    assert explicit_settings.DATABASE_URL == "sqlite+aiosqlite:////tmp/incubrix.db"
    assert explicit_settings.SYNC_DATABASE_URL == "sqlite:///custom_explicit.db"
