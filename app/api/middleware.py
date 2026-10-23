"""Middleware for Correlation IDs, Idempotency enforcement, and structured error handling."""

import uuid
import asyncio
import time
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from app.rules.errors import ConnectorException, ErrorCode
from app.storage.idempotency_store import IdempotencyStore
from app.logging_conf import logger, current_correlation_id
from app.config import settings


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        token = current_correlation_id.set(correlation_id)

        try:
            response: Response = await call_next(request)
            response.headers["X-Correlation-Id"] = correlation_id
            return response
        finally:
            current_correlation_id.reset(token)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Enforces required Idempotency-Key header on all POST requests under /api/v1/.
    Prevents duplicate execution and returns cached result on retry.
    Survives service restarts through persistent database storage.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        # Apply to all POST requests under /api/v1/ (exempting nothing) and /connector/v1/.../publish
        is_api_v1 = method == "POST" and path.startswith("/api/v1/")
        is_connector_publish = method == "POST" and path.startswith("/connector/v1/") and path.endswith("/publish")

        if is_api_v1 or is_connector_publish:
            idempotency_key = request.headers.get("Idempotency-Key")
            body_bytes = await request.body()

            if not idempotency_key and is_connector_publish:
                try:
                    import json
                    body_json = json.loads(body_bytes.decode("utf-8"))
                    idempotency_key = body_json.get("idempotency_key")
                except Exception:
                    pass

            if is_api_v1 and (not idempotency_key or not idempotency_key.strip()):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": ErrorCode.DEST_SPEC_VIOLATION.value,
                            "message": "Idempotency-Key header is required for all POST requests under /api/v1/",
                            "retryable": False,
                            "details": {"path": path}
                        },
                        "code": ErrorCode.DEST_SPEC_VIOLATION.value,
                        "message": "Idempotency-Key header is required for all POST requests under /api/v1/",
                        "retryable": False,
                        "details": {"path": path}
                    }
                )

            if not idempotency_key:
                # Other non-publish connector routes (e.g. validate, get_status) don't strictly require idempotency
                async def receive():
                    return {"type": "http.request", "body": body_bytes, "more_body": False}
                request = Request(request.scope, receive)
                return await call_next(request)

            # Reconstruct request receive stream so downstream route handlers (JSON or multipart form) can read body
            async def receive():
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            request = Request(request.scope, receive)

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
                        "error": {
                            "code": ErrorCode.DEST_SPEC_VIOLATION.value,
                            "message": f"Idempotency key '{idempotency_key}' was reused with materially different request payload.",
                            "retryable": False,
                            "details": {}
                        },
                        "code": ErrorCode.DEST_SPEC_VIOLATION.value,
                        "message": f"Idempotency key '{idempotency_key}' was reused with materially different request payload.",
                        "retryable": False
                    }
                )

            elif status_type == "OUTCOME_UNKNOWN":
                logger.info(f"Retrying idempotency key '{idempotency_key}' whose previous outcome was unknown. Flagging for platform reconcile.")
                request.state.is_retry_after_unknown = True
                request.state.idempotency_key = idempotency_key

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
                        "error": {
                            "code": ErrorCode.RATE_LIMITED.value,
                            "message": f"Concurrent in-flight request for idempotency key '{idempotency_key}'. Please retry shortly.",
                            "retryable": True,
                            "details": {}
                        },
                        "code": ErrorCode.RATE_LIMITED.value,
                        "message": f"Concurrent in-flight request for idempotency key '{idempotency_key}'. Please retry shortly.",
                        "retryable": True
                    }
                )

            # status_type in ("NEW", "OUTCOME_UNKNOWN"): execute route
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
                elif response.status_code in (408, 504) or "timeout" in full_body.decode("utf-8", errors="replace").lower():
                    await IdempotencyStore.record_outcome_unknown(idempotency_key)
                else:
                    await IdempotencyStore.record_failed(idempotency_key)

                return new_response

            except asyncio.TimeoutError:
                await IdempotencyStore.record_outcome_unknown(idempotency_key)
                raise
            except Exception as exc:
                if "timeout" in str(exc).lower():
                    await IdempotencyStore.record_outcome_unknown(idempotency_key)
                else:
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


class DemoAuthAndRateLimitMiddleware(BaseHTTPMiddleware):
    """Enforces demo API token authentication and rate limiting for live demo deployments."""

    def __init__(self, app):
        super().__init__(app)
        self._request_history = {}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Public paths exempt from demo authentication
        public_prefixes = ("/health", "/ready", "/docs", "/redoc", "/openapi", "/robots.txt", "/mock")
        if any(path.startswith(prefix) for prefix in public_prefixes):
            return await call_next(request)

        # 1. API Token Check (enforced when DEMO_API_TOKEN is configured)
        if settings.DEMO_API_TOKEN:
            auth_header = request.headers.get("Authorization", "")
            api_key_header = request.headers.get("X-API-Key", "")
            token = ""
            if auth_header.startswith("Bearer "):
                token = auth_header.split("Bearer ", 1)[1].strip()
            elif api_key_header:
                token = api_key_header.strip()

            if token != settings.DEMO_API_TOKEN:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "code": ErrorCode.UNAUTHORIZED.value,
                            "message": "Missing or invalid demo API token. Provide Authorization: Bearer <token>",
                            "retryable": False,
                            "details": {}
                        },
                        "code": ErrorCode.UNAUTHORIZED.value,
                        "message": "Missing or invalid demo API token. Provide Authorization: Bearer <token>"
                    }
                )

        # 2. Rate Limiting Check (requests per minute per client)
        now = time.time()
        client_ip = request.client.host if request.client else "global"

        if client_ip not in self._request_history:
            self._request_history[client_ip] = []
        self._request_history[client_ip] = [t for t in self._request_history[client_ip] if now - t < 60.0]

        limit = settings.DEMO_RATE_LIMIT_PER_MINUTE
        if len(self._request_history[client_ip]) >= limit:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": "10"},
                content={
                    "error": {
                        "code": ErrorCode.RATE_LIMITED.value,
                        "message": "Rate limit exceeded. Too many requests per minute.",
                        "retryable": True,
                        "details": {"retry_after_seconds": 10}
                    },
                    "code": ErrorCode.RATE_LIMITED.value,
                    "message": "Rate limit exceeded. Too many requests per minute."
                }
            )

        self._request_history[client_ip].append(now)
        return await call_next(request)
