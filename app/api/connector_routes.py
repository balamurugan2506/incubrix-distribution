"""Connector HTTP Contract routes matching POST /connector/v1/{connector_key}/{method}."""

from fastapi import APIRouter, HTTPException, status, Request
from typing import Any, Union
from pydantic import ValidationError

from app.connectors.registry import registry
from app.schemas.connector import (
    ValidateRequest,
    ValidateResult,
    PublishRequest,
    PublishResult,
    StatusRequest,
    StatusResult,
    DeleteRequest,
    DeleteResult,
    FetchMetricsRequest,
    MetricsResult,
    RefreshAuthRequest,
    RefreshAuthResult,
    BuildAssistPackRequest,
    AssistPackResult
)
from app.rules.errors import ConnectorException, ErrorCode

router = APIRouter(prefix="/connector/v1", tags=["Connector Contract"])


@router.post("/{connector_key}/validate", response_model=ValidateResult)
async def validate_post(connector_key: str, payload: ValidateRequest):
    connector = registry.get_connector(connector_key)
    return await connector.validate(payload.rendition, payload.destination, payload.connection)


from app.rules.engine import rules_engine

@router.post("/{connector_key}/publish", response_model=PublishResult)
async def publish_post(connector_key: str, payload: PublishRequest, request: Request):
    connector = registry.get_connector(connector_key)

    # Enforce destination posting rules (fail-closed, limits, links, promo, AI disclosure)
    await rules_engine.check_rules(
        rendition=payload.rendition,
        destination=payload.destination,
        db=None,
        is_automated_request=True
    )

    # If retry after timeout or unknown outcome, query platform first to prevent duplication
    if getattr(request.state, "is_retry_after_unknown", False):
        reconciled = await connector.reconcile(
            payload.rendition,
            payload.destination,
            payload.connection,
            payload.idempotency_key
        )
        if reconciled:
            return reconciled

    return await connector.publish(
        payload.rendition,
        payload.destination,
        payload.connection,
        payload.idempotency_key
    )


@router.post("/{connector_key}/get_status", response_model=StatusResult)
async def get_status_post(connector_key: str, payload: StatusRequest):
    connector = registry.get_connector(connector_key)
    return await connector.get_status(payload.platform_post_id, payload.connection)


@router.post("/{connector_key}/delete", response_model=DeleteResult)
async def delete_post(connector_key: str, payload: DeleteRequest):
    connector = registry.get_connector(connector_key)
    return await connector.delete(payload.platform_post_id, payload.connection)


@router.post("/{connector_key}/fetch_metrics", response_model=MetricsResult)
async def fetch_metrics_post(connector_key: str, payload: FetchMetricsRequest):
    connector = registry.get_connector(connector_key)
    return await connector.fetch_metrics(payload.platform_post_id, payload.connection, payload.since)


@router.post("/{connector_key}/refresh_auth", response_model=RefreshAuthResult)
async def refresh_auth_post(connector_key: str, payload: RefreshAuthRequest):
    connector = registry.get_connector(connector_key)
    return await connector.refresh_auth(payload.connection)


@router.post("/{connector_key}/build_assist_pack", response_model=AssistPackResult)
async def build_assist_pack_post(connector_key: str, payload: BuildAssistPackRequest):
    connector = registry.get_connector(connector_key)
    return await connector.build_assist_pack(payload.rendition, payload.destination)


# Manifest Inspection
@router.get("/manifests")
async def list_manifests():
    return registry.list_manifests()


@router.get("/{connector_key}/manifest")
async def get_manifest(connector_key: str):
    return registry.get_manifest(connector_key)
