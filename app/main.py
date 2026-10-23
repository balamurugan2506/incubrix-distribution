"""Main FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.logging_conf import logger
from app.api.middleware import CorrelationIdMiddleware, IdempotencyMiddleware, connector_exception_handler
from app.rules.errors import ConnectorException
from app.api.health import router as health_router
from app.api.connector_routes import router as connector_router
from app.api.destinations import router as destinations_router
from app.api.jobs import router as jobs_router
from app.api.certification import router as certification_router
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

# Middleware
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(IdempotencyMiddleware)

# Exception handlers
app.add_exception_handler(ConnectorException, connector_exception_handler)

# Routers
app.include_router(health_router)
app.include_router(connector_router)
app.include_router(destinations_router)
app.include_router(jobs_router)
app.include_router(certification_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.APP_DEBUG)
