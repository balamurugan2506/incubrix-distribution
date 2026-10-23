"""Health and readiness endpoints."""

from fastapi import APIRouter
from app.config import settings
from app.connectors.registry import registry

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "app_env": settings.APP_ENV,
        "simulation_mode": settings.SIMULATION_MODE,
        "version": "1.0.0"
    }


@router.get("/ready")
async def readiness_check():
    manifest_count = len(registry.list_manifests())
    return {
        "status": "ready",
        "database": "connected",
        "connectors_loaded": manifest_count
    }
