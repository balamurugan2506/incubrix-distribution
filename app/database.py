"""SQLAlchemy asynchronous and synchronous database engine setup."""

from pathlib import Path
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from app.config import settings
from app.logging_conf import logger

Base = declarative_base()


def ensure_db_directory(db_url: str) -> Optional[Path]:
    """Ensure the parent directory for a SQLite database file exists.

    Safely ignores in-memory databases (:memory: or None) and non-SQLite databases.
    Handles both relative and absolute paths across platforms.
    """
    if not db_url:
        return None
    try:
        url = make_url(db_url)
    except Exception:
        return None

    if not url.drivername.startswith("sqlite"):
        return None

    db_path = url.database
    if not db_path or db_path == ":memory:":
        return None

    try:
        parent_dir = Path(db_path).resolve().parent
        if str(parent_dir) and not parent_dir.exists():
            parent_dir.mkdir(parents=True, exist_ok=True)
        return parent_dir
    except Exception as exc:
        logger.warning(f"Could not create database directory for {db_url}: {exc}")
        return None


# Ensure database directory exists before connecting
ensure_db_directory(settings.DATABASE_URL)
if settings.SYNC_DATABASE_URL:
    ensure_db_directory(settings.SYNC_DATABASE_URL)

# Async engine for FastAPI route handlers
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Sync engine for scripts / migrations if needed
sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.SYNC_DATABASE_URL else {}
)

SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)


async def get_db():
    """FastAPI dependency yielding an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db(engine=None):
    """Create all tables on application startup and ensure schema completeness."""
    target_engine = engine or async_engine
    ensure_db_directory(str(target_engine.url))

    # Ensure all models are registered on Base
    import app.models  # noqa: F401
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE destinations ADD COLUMN frequency_period_hours INTEGER DEFAULT 24"))
        except Exception:
            pass
        try:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE destinations ADD COLUMN status VARCHAR(32) DEFAULT 'active'"))
        except Exception:
            pass
        try:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE destinations ADD COLUMN catalogue_only BOOLEAN DEFAULT 0"))
        except Exception:
            pass
