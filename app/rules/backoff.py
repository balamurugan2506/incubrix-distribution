"""Exponential backoff and retry helper respecting 429 Retry-After and 5-failure limit."""

import asyncio
from typing import Callable, Any, TypeVar, Optional
from app.rules.errors import ConnectorException, ErrorCode
from app.logging_conf import logger

T = TypeVar("T")


class RetryPolicy:
    MAX_ATTEMPTS = 5
    INITIAL_DELAY_SECONDS = 0.5
    BACKOFF_FACTOR = 2.0
    MAX_DELAY_SECONDS = 30.0


async def execute_with_retry(
    func: Callable[[], Any],
    operation_name: str = "platform_operation",
    max_retries: int = RetryPolicy.MAX_ATTEMPTS
) -> Any:
    """
    Executes an async operation with exponential backoff.
    Aborts immediately if error is non-retryable (content rejection, bad auth, policy violations).
    Stops after 5 consecutive failures.
    """
    attempt = 0
    delay = RetryPolicy.INITIAL_DELAY_SECONDS

    while attempt < max_retries:
        attempt += 1
        try:
            return await func()
        except ConnectorException as exc:
            if not exc.retryable:
                logger.info(f"Operation '{operation_name}' failed with non-retryable error [{exc.code.value}]. Aborting retries.")
                raise exc

            if attempt >= max_retries:
                logger.error(f"Operation '{operation_name}' exhausted all {max_retries} attempts.")
                raise exc

            # Determine wait time respecting 429 Retry-After if present
            retry_after = exc.details.get("retry_after")
            sleep_time = float(retry_after) if retry_after is not None else delay

            logger.warning(
                f"Attempt {attempt}/{max_retries} failed for '{operation_name}' [{exc.code.value}]. "
                f"Backing off for {sleep_time:.2f}s before retry..."
            )
            await asyncio.sleep(sleep_time)
            delay = min(delay * RetryPolicy.BACKOFF_FACTOR, RetryPolicy.MAX_DELAY_SECONDS)

    raise ConnectorException(
        code=ErrorCode.PLATFORM_UNAVAILABLE,
        message=f"Consecutive failures exceeded threshold ({max_retries}) for {operation_name}",
        retryable=False
    )
