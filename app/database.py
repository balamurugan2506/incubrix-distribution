"""SQLAlchemy asynchronous and synchronous database engine setup."""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import create_engine
from app.config import settings

Base = declarative_base()

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


async def init_db():
    """Create all tables on application startup and ensure schema completeness."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight migration for newly added columns if table pre-existed
        try:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE destinations ADD COLUMN frequency_period_hours INTEGER DEFAULT 24"))
        except Exception:
            pass
