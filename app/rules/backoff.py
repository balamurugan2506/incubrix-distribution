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
    max_retries: int = RetryPolicy.MAX_ATTEMPTS,
    is_idempotent_operation: bool = True,
    reconcile_func: Optional[Callable[[], Any]] = None
) -> Any:
    """
    Executes an async operation with exponential backoff.
    Aborts immediately if error is non-retryable (content rejection, bad auth, policy violations).
    Never retries a non-idempotent create blindly without reconciliation.
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

            # Never retry non-idempotent create blindly inside backoff
            if not is_idempotent_operation:
                if reconcile_func:
                    logger.info(f"Reconciling unknown outcome for non-idempotent '{operation_name}' before retry...")
                    try:
                        reconciled = await reconcile_func()
                        if reconciled:
                            logger.info(f"Reconciliation succeeded for '{operation_name}', found existing post.")
                            return reconciled
                    except Exception as r_exc:
                        logger.warning(f"Reconciliation probe failed: {r_exc}")
                else:
                    logger.warning(f"Refusing to blindly retry non-idempotent create operation '{operation_name}'.")
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
