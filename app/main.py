"""Main FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.logging_conf import logger
from app.api.middleware import (
    CorrelationIdMiddleware,
    IdempotencyMiddleware,
    DemoAuthAndRateLimitMiddleware,
    connector_exception_handler
)
from app.rules.errors import ConnectorException
from app.api.health import router as health_router
from app.api.connector_routes import router as connector_router
from app.api.destinations import router as destinations_router
from app.api.jobs import router as jobs_router
from app.api.certification import router as certification_router
from app.api.evidence import router as evidence_router
from app.api.alerts import router as alerts_router
from app.api.recommendations import router as recommendations_router
from app.api.demo import router as demo_router
from app.database import init_db
import app.connectors  # Register connectors and load manifests


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting IncuBrix Distribution Network service (Simulation={settings.SIMULATION_MODE})")
    await init_db()
    yield
    logger.info("Shutting down IncuBrix Distribution Network service")


app = FastAPI(
    title="IncuBrix Distribution Network API",
    description="Production-grade long-tail destination network for multichannel content distribution.",
    version="1.0.0",
    openapi_version="3.1.0",
    lifespan=lifespan
)

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi import Request
from fastapi.responses import JSONResponse
from app.rules.errors import ErrorCode

from fastapi.middleware.cors import CORSMiddleware

# Middleware (Order: Outer to Inner -> CORSMiddleware wraps DemoAuth -> Idempotency -> CorrelationId)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(DemoAuthAndRateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID", "Idempotency-Key", "X-Cache"],
)

# Exception handlers
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": ErrorCode.DEST_SPEC_VIOLATION.value,
                "message": "Request validation failed",
                "retryable": False,
                "details": {"errors": exc.errors()}
            },
            "code": ErrorCode.DEST_SPEC_VIOLATION.value,
            "message": "Request validation failed",
            "retryable": False,
            "details": {"errors": exc.errors()}
        }
    )

async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = ErrorCode.DEST_SPEC_VIOLATION.value
    if exc.status_code == 401:
        code = ErrorCode.UNAUTHORIZED.value
    elif exc.status_code == 429:
        code = ErrorCode.RATE_LIMITED.value
    elif exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code >= 500:
        code = ErrorCode.PLATFORM_UNAVAILABLE.value

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": str(exc.detail),
                "retryable": exc.status_code in (429, 503),
                "details": {}
            },
            "code": code,
            "message": str(exc.detail),
            "detail": str(exc.detail),
            "retryable": exc.status_code in (429, 503),
            "details": {}
        }
    )

app.add_exception_handler(ConnectorException, connector_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)

# Routers
app.include_router(health_router)
app.include_router(connector_router)
app.include_router(destinations_router)
app.include_router(jobs_router)
app.include_router(certification_router)
app.include_router(evidence_router)
app.include_router(alerts_router)
app.include_router(recommendations_router)
app.include_router(demo_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.APP_DEBUG)
