"""Middleware for Correlation IDs, Idempotency enforcement, and structured error handling."""

import uuid
import asyncio
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from app.rules.errors import ConnectorException, ErrorCode
from app.storage.idempotency_store import IdempotencyStore
from app.logging_conf import logger


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        response: Response = await call_next(request)
        response.headers["X-Correlation-Id"] = correlation_id
        return response


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Enforces required Idempotency-Key header on all POST requests under /api/v1/.
    Prevents duplicate execution and returns cached result on retry.
    Survives service restarts through persistent database storage.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        # Only apply to POST under /api/v1/ (excluding multipart CSV upload)
        if method == "POST" and path.startswith("/api/v1/"):
            if "import-csv" in path:
                return await call_next(request)

            idempotency_key = request.headers.get("Idempotency-Key")
            if not idempotency_key or not idempotency_key.strip():
                return JSONResponse(
                    status_code=400,
                    content={
                        "code": ErrorCode.DEST_SPEC_VIOLATION.value,
                        "message": "Idempotency-Key header is required for all POST requests under /api/v1/",
                        "retryable": False,
                        "details": {"path": path}
                    }
                )

            # Read request body
            body_bytes = await request.body()

            status_type, cached_code, cached_body = await IdempotencyStore.get_or_create_record(
                idempotency_key, path, body_bytes
            )

            if status_type == "CACHED":
                logger.info(f"Idempotency hit for key '{idempotency_key}' on {path}. Returning cached response.")
                return Response(
                    content=cached_body,
                    status_code=cached_code or 200,
                    media_type="application/json",
                    headers={
                        "X-Cache": "IDEMPOTENT-HIT",
                        "Idempotency-Key": idempotency_key
                    }
                )

            elif status_type == "CONFLICT":
                return JSONResponse(
                    status_code=409,
                    content={
                        "code": ErrorCode.DEST_SPEC_VIOLATION.value,
                        "message": f"Idempotency key '{idempotency_key}' was reused with materially different request payload.",
                        "retryable": False
                    }
                )

            elif status_type == "PENDING":
                # In-flight concurrent request with the same key
                for _ in range(10):
                    await asyncio.sleep(0.2)
                    check_type, c_code, c_body = await IdempotencyStore.get_or_create_record(
                        idempotency_key, path, body_bytes
                    )
                    if check_type == "CACHED":
                        return Response(
                            content=c_body,
                            status_code=c_code or 200,
                            media_type="application/json",
                            headers={"X-Cache": "IDEMPOTENT-HIT", "Idempotency-Key": idempotency_key}
                        )

                return JSONResponse(
                    status_code=409,
                    content={
                        "code": ErrorCode.PLATFORM_RATE_LIMIT.value,
                        "message": f"Concurrent in-flight request for idempotency key '{idempotency_key}'. Please retry shortly.",
                        "retryable": True
                    }
                )

            # status_type == "NEW": execute route
            try:
                response: Response = await call_next(request)

                # Capture body for caching
                resp_body = [chunk async for chunk in response.body_iterator]
                full_body = b"".join(resp_body)

                # Reconstruct response since body was consumed
                new_response = Response(
                    content=full_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type
                )

                if response.status_code < 400:
                    await IdempotencyStore.record_completed(
                        idempotency_key,
                        response.status_code,
                        full_body.decode("utf-8", errors="replace")
                    )
                else:
                    await IdempotencyStore.record_failed(idempotency_key)

                return new_response

            except Exception:
                await IdempotencyStore.record_failed(idempotency_key)
                raise

        return await call_next(request)


async def connector_exception_handler(request: Request, exc: ConnectorException):
    correlation_id = getattr(request.state, "correlation_id", None)
    logger.warning(
        f"ConnectorException [{exc.code.value}]: {exc.message}",
        extra={"correlation_id": correlation_id}
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
        headers={"X-Correlation-Id": correlation_id or ""}
    )
