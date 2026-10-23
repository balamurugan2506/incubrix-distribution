"""Generic HMAC-SHA256 Signed Webhook Connector."""

import hmac
import hashlib
import time
import json
import httpx
from typing import Optional, List
from app.connectors.base import BaseConnector
from app.schemas.connector import (
    RenditionSchema,
    DestinationSchema,
    ConnectionSchema,
    ValidateResult,
    PublishResult,
    StatusResult,
    DeleteResult
)
from app.rules.errors import ConnectorException, ErrorCode
from app.config import settings


def compute_hmac_signature(secret: str, payload_bytes: bytes, timestamp: str) -> str:
    """Compute HMAC-SHA256 signature over timestamp.payload."""
    message = f"{timestamp}.".encode("utf-8") + payload_bytes
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_hmac_signature(secret: str, payload_bytes: bytes, timestamp: str, signature_header: str) -> bool:
    """Verify incoming HMAC signature with constant-time comparison."""
    expected = compute_hmac_signature(secret, payload_bytes, timestamp)
    return hmac.compare_digest(expected, signature_header)


class SignedWebhookConnector(BaseConnector):
    key = "signed_webhook"

    def _get_secret(self, connection: ConnectionSchema) -> str:
        secret = connection.credentials.get("hmac_secret") or settings.INCUBRIX_WEBHOOK_SECRET
        if not secret:
            raise ConnectorException(
                code=ErrorCode.CONNECTION_AUTH_EXPIRED,
                message="HMAC secret missing for signed webhook",
                retryable=False,
                status_code=401
            )
        return secret

    def _get_endpoint(self, destination: DestinationSchema, connection: ConnectionSchema) -> str:
        endpoint = (
            destination.instance_config.get("endpoint_url") or
            connection.base_url or
            destination.url or
            settings.WEBHOOK_TEST_URL
        )
        return endpoint.rstrip("/")

    async def validate(
        self,
        rendition: RenditionSchema,
        destination: DestinationSchema,
        connection: ConnectionSchema
    ) -> ValidateResult:
        violations: List[str] = []

        if not rendition.body and not rendition.title:
            violations.append("Webhook payload requires at least title or body content")

        endpoint = self._get_endpoint(destination, connection)
        if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
            violations.append(f"Invalid webhook URL format: {endpoint}")

        return ValidateResult(ok=len(violations) == 0, violations=violations)

    async def publish(
        self,
        rendition: RenditionSchema,
        destination: DestinationSchema,
        connection: ConnectionSchema,
        idempotency_key: str
    ) -> PublishResult:
        val = await self.validate(rendition, destination, connection)
        if not val.ok:
            raise ConnectorException(
                code=ErrorCode.DEST_SPEC_VIOLATION,
                message=f"Webhook validation failed: {'; '.join(val.violations)}",
                retryable=False,
                details={"violations": val.violations},
                status_code=422
            )

        endpoint = self._get_endpoint(destination, connection)
        secret = self._get_secret(connection)

        timestamp = str(int(time.time()))
        body_dict = {
            "event": "distribution.publish",
            "idempotency_key": idempotency_key,
            "timestamp": timestamp,
            "destination": {
                "name": destination.name,
                "url": destination.url,
                "surface": destination.surface
            },
            "rendition": rendition.model_dump()
        }
        body_bytes = json.dumps(body_dict, sort_keys=True).encode("utf-8")
        signature = compute_hmac_signature(secret, body_bytes, timestamp)

        headers = {
            "Content-Type": "application/json",
            "X-IncuBrix-Signature": signature,
            "X-IncuBrix-Timestamp": timestamp,
            "Idempotency-Key": idempotency_key
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(endpoint, content=body_bytes, headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Webhook delivery failed: {str(exc)}",
                    retryable=True,
                    status_code=503
                )

        if resp.status_code in (200, 201, 202):
            try:
                data = resp.json()
                post_id = str(data.get("id") or idempotency_key)
                live_url = data.get("url") or f"{endpoint}/{post_id}"
            except Exception:
                post_id = idempotency_key
                live_url = endpoint

            return PublishResult(
                platform_post_id=post_id,
                live_url=live_url,
                status="published"
            )

        self._handle_http_error(resp)

    async def get_status(
        self,
        platform_post_id: str,
        connection: ConnectionSchema
    ) -> StatusResult:
        endpoint = (connection.base_url or settings.WEBHOOK_TEST_URL).rstrip("/")
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(f"{endpoint}/{platform_post_id}")
            except httpx.RequestError:
                return StatusResult(status="published", live_url=f"{endpoint}/{platform_post_id}")

        if resp.status_code == 200:
            data = resp.json()
            return StatusResult(status=data.get("status", "published"), live_url=data.get("live_url", f"{endpoint}/{platform_post_id}"))
        elif resp.status_code == 404:
            return StatusResult(status="not_found", live_url="")
        return StatusResult(status="unknown", live_url="")

    async def delete(
        self,
        platform_post_id: str,
        connection: ConnectionSchema
    ) -> DeleteResult:
        endpoint = (connection.base_url or settings.WEBHOOK_TEST_URL).rstrip("/")
        secret = self._get_secret(connection)
        timestamp = str(int(time.time()))
        body_dict = {"event": "distribution.delete", "platform_post_id": platform_post_id}
        body_bytes = json.dumps(body_dict).encode("utf-8")
        signature = compute_hmac_signature(secret, body_bytes, timestamp)

        headers = {
            "Content-Type": "application/json",
            "X-IncuBrix-Signature": signature,
            "X-IncuBrix-Timestamp": timestamp
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.delete(f"{endpoint}/{platform_post_id}", headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Webhook delete call failed: {str(exc)}",
                    retryable=True,
                    status_code=503
                )

        if resp.status_code in (200, 204):
            return DeleteResult(deleted=True)
        elif resp.status_code == 404:
            return DeleteResult(deleted=True)

        self._handle_http_error(resp)

    def _handle_http_error(self, resp: httpx.Response):
        status = resp.status_code
        text = resp.text
        if status in (401, 403):
            raise ConnectorException(
                code=ErrorCode.CONNECTION_AUTH_EXPIRED,
                message=f"Webhook authentication/signature rejected: {text}",
                retryable=False,
                status_code=status
            )
        elif status == 422:
            raise ConnectorException(
                code=ErrorCode.PLATFORM_CONTENT_REJECTED,
                message=f"Webhook receiver rejected content: {text}",
                retryable=False,
                status_code=status
            )
        elif status == 429:
            retry_after = resp.headers.get("Retry-After", "5")
            raise ConnectorException(
                code=ErrorCode.PLATFORM_RATE_LIMIT,
                message=f"Webhook receiver rate limited. Retry after {retry_after}s",
                retryable=True,
                details={"retry_after": int(retry_after) if retry_after.isdigit() else 5},
                status_code=status
            )
        elif status >= 500:
            raise ConnectorException(
                code=ErrorCode.PLATFORM_UNAVAILABLE,
                message=f"Webhook endpoint returned server error ({status}): {text}",
                retryable=True,
                status_code=status
            )
        else:
            raise ConnectorException(
                code=ErrorCode.DEST_SPEC_VIOLATION,
                message=f"Webhook error ({status}): {text}",
                retryable=False,
                status_code=status
            )
