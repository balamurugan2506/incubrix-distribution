"""Unit tests for exponential backoff and retry policy."""

import pytest
from app.rules.backoff import execute_with_retry
from app.rules.errors import ConnectorException, ErrorCode


@pytest.mark.asyncio
async def test_non_retryable_error_aborts_immediately():
    calls = 0

    async def failing_op():
        nonlocal calls
        calls += 1
        raise ConnectorException(
            code=ErrorCode.DEST_SPEC_VIOLATION,
            message="Content invalid",
            retryable=False
        )

    with pytest.raises(ConnectorException) as exc:
        await execute_with_retry(failing_op, max_retries=5)

    assert exc.value.code == ErrorCode.DEST_SPEC_VIOLATION
    assert calls == 1  # Did not retry


@pytest.mark.asyncio
async def test_retryable_succeeds_after_attempts():
    calls = 0

    async def flaky_op():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectorException(
                code=ErrorCode.PLATFORM_RATE_LIMIT,
                message="Rate limited",
                retryable=True,
                details={"retry_after": 0.01}
            )
        return {"status": "success", "attempts": calls}

    res = await execute_with_retry(flaky_op, max_retries=5)
    assert res["status"] == "success"
    assert res["attempts"] == 3


@pytest.mark.asyncio
async def test_stops_after_five_consecutive_failures():
    calls = 0

    async def permanently_failing_retryable():
        nonlocal calls
        calls += 1
        raise ConnectorException(
            code=ErrorCode.PLATFORM_UNAVAILABLE,
            message="Platform 503",
            retryable=True,
            details={"retry_after": 0.01}
        )

    with pytest.raises(ConnectorException) as exc:
        await execute_with_retry(permanently_failing_retryable, max_retries=5)

    assert calls == 5
    assert exc.value.code == ErrorCode.PLATFORM_UNAVAILABLE
