"""Persistent Idempotency store and verification logic."""

import hashlib
import json
import asyncio
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.idempotency import IdempotencyRecordModel
from app.logging_conf import logger


def calculate_request_hash(path: str, body_bytes: bytes) -> str:
    """Calculate SHA-256 hash of request path + body bytes."""
    hasher = hashlib.sha256()
    hasher.update(path.encode("utf-8"))
    hasher.update(b":")
    hasher.update(body_bytes)
    return hasher.hexdigest()


class IdempotencyStore:
    """Handles thread-safe, restart-proof idempotency checks."""

    @staticmethod
    async def get_or_create_record(
        key: str,
        path: str,
        body_bytes: bytes
    ) -> Tuple[str, Optional[int], Optional[str]]:
        """
        Check idempotency status.
        Returns:
            ("NEW", None, None) if this is a fresh key.
            ("CACHED", response_code, response_body) if previously completed with identical payload.
            ("CONFLICT", None, None) if key was reused with materially different payload.
            ("PENDING", None, None) if currently being executed concurrently.
        """
        req_hash = calculate_request_hash(path, body_bytes)

        async with AsyncSessionLocal() as session:
            stmt = select(IdempotencyRecordModel).where(IdempotencyRecordModel.idempotency_key == key)
            res = await session.execute(stmt)
            record = res.scalar_one_or_none()

            if not record:
                # Fresh key, create pending record
                new_record = IdempotencyRecordModel(
                    idempotency_key=key,
                    request_hash=req_hash,
                    status="pending"
                )
                session.add(new_record)
                try:
                    await session.commit()
                    return "NEW", None, None
                except Exception:
                    # Concurrently inserted, re-read
                    await session.rollback()
                    res = await session.execute(stmt)
                    record = res.scalar_one_or_none()

            if record.request_hash != req_hash:
                logger.warning(f"Idempotency conflict for key '{key}': payload hash mismatch.")
                return "CONFLICT", None, None

            if record.status == "completed":
                return "CACHED", record.response_code, record.response_body

            if record.status == "outcome_unknown":
                return "OUTCOME_UNKNOWN", record.response_code, record.response_body

            # In flight
            return "PENDING", None, None

    @staticmethod
    async def record_completed(
        key: str,
        response_code: int,
        response_body: str
    ) -> None:
        """Mark idempotency record as completed with stored response."""
        async with AsyncSessionLocal() as session:
            stmt = select(IdempotencyRecordModel).where(IdempotencyRecordModel.idempotency_key == key)
            res = await session.execute(stmt)
            record = res.scalar_one_or_none()
            if record:
                record.status = "completed"
                record.response_code = response_code
                record.response_body = response_body
                record.completed_at = datetime.now(timezone.utc)
                await session.commit()

    @staticmethod
    async def record_outcome_unknown(key: str) -> None:
        """Mark idempotency record as outcome_unknown so retries trigger platform reconciliation."""
        async with AsyncSessionLocal() as session:
            stmt = select(IdempotencyRecordModel).where(IdempotencyRecordModel.idempotency_key == key)
            res = await session.execute(stmt)
            record = res.scalar_one_or_none()
            if record:
                record.status = "outcome_unknown"
                await session.commit()

    @staticmethod
    async def record_failed(key: str) -> None:
        """Remove or mark failed idempotency record so retries are allowed."""
        async with AsyncSessionLocal() as session:
            stmt = select(IdempotencyRecordModel).where(IdempotencyRecordModel.idempotency_key == key)
            res = await session.execute(stmt)
            record = res.scalar_one_or_none()
            if record:
                record.status = "failed"
                await session.commit()
