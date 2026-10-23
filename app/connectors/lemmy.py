"""Lemmy Fediverse API Connector."""

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
    DeleteResult,
    MetricsResult
)
from app.rules.errors import ConnectorException, ErrorCode
from app.config import settings


class LemmyConnector(BaseConnector):
    key = "lemmy"

    def _get_base_url(self, connection: ConnectionSchema) -> str:
        return (connection.base_url or settings.get_lemmy_base_url()).rstrip("/")

    def _get_token(self, connection: ConnectionSchema) -> str:
        token = connection.credentials.get("auth_token") or settings.get_lemmy_token()
        if not token:
            raise ConnectorException(
                code=ErrorCode.CONNECTION_AUTH_EXPIRED,
                message="Lemmy auth_token missing from connection credentials",
                retryable=False,
                status_code=401
            )
        return token

    async def validate(
        self,
        rendition: RenditionSchema,
        destination: DestinationSchema,
        connection: ConnectionSchema
    ) -> ValidateResult:
        violations: List[str] = []

        if not rendition.title or len(rendition.title.strip()) < 3:
            violations.append("Lemmy post title must be at least 3 characters")
        elif len(rendition.title) > 200:
            violations.append("Lemmy post title cannot exceed 200 characters")

        if rendition.body and len(rendition.body) > 40000:
            violations.append("Lemmy post body exceeds 40,000 characters limit")

        community_id = destination.instance_config.get("community_id")
        community_name = destination.instance_config.get("community_name")
        if not community_id and not community_name:
            violations.append("Lemmy requires community_id or community_name in destination configuration")

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
                message=f"Lemmy validation failed: {'; '.join(val.violations)}",
                retryable=False,
                details={"violations": val.violations},
                status_code=422
            )

        base_url = self._get_base_url(connection)
        token = self._get_token(connection)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key
        }

        payload = {
            "name": rendition.title,
            "body": rendition.body,
            "community_id": destination.instance_config.get("community_id", 1),
            "url": rendition.canonical_url,
            "auth": token
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(f"{base_url}/api/v3/post", json=payload, headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Lemmy server connection failed: {str(exc)}",
                    retryable=True,
                    status_code=503
                )

        if resp.status_code in (200, 201):
            data = resp.json()
            post_data = data.get("post_view", {}).get("post", {})
            post_id = str(post_data.get("id"))
            live_url = f"{base_url}/post/{post_id}"
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
        base_url = self._get_base_url(connection)
        token = self._get_token(connection)
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(f"{base_url}/api/v3/post?id={platform_post_id}", headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Lemmy get_status failed: {str(exc)}",
                    retryable=True,
                    status_code=503
                )

        if resp.status_code == 200:
            return StatusResult(status="published", live_url=f"{base_url}/post/{platform_post_id}")
        elif resp.status_code == 404:
            return StatusResult(status="not_found", live_url="")

        self._handle_http_error(resp)

    async def delete(
        self,
        platform_post_id: str,
        connection: ConnectionSchema
    ) -> DeleteResult:
        base_url = self._get_base_url(connection)
        token = self._get_token(connection)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        payload = {
            "post_id": int(platform_post_id) if platform_post_id.isdigit() else 1,
            "deleted": True,
            "auth": token
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(f"{base_url}/api/v3/post/delete", json=payload, headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Lemmy delete failed: {str(exc)}",
                    retryable=True,
                    status_code=503
                )

        if resp.status_code in (200, 204):
            return DeleteResult(deleted=True)
        elif resp.status_code == 404:
            return DeleteResult(deleted=True)

        self._handle_http_error(resp)

    async def fetch_metrics(
        self,
        platform_post_id: str,
        connection: ConnectionSchema,
        since: Optional[str] = None
    ) -> MetricsResult:
        base_url = self._get_base_url(connection)
        token = self._get_token(connection)
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(f"{base_url}/api/v3/post?id={platform_post_id}", headers=headers)
            except httpx.RequestError:
                return MetricsResult()

        if resp.status_code == 200:
            counts = resp.json().get("post_view", {}).get("counts", {})
            return MetricsResult(
                views=0,
                likes=int(counts.get("upvotes", 0)),
                comments=int(counts.get("comments", 0)),
                shares=0,
                saves=0,
                watch_time_s=0,
                clicks=0
            )
        return MetricsResult()

    def _handle_http_error(self, resp: httpx.Response):
        status = resp.status_code
        text = resp.text
        if status in (401, 403):
            raise ConnectorException(
                code=ErrorCode.CONNECTION_AUTH_EXPIRED,
                message=f"Lemmy authentication expired or invalid: {text}",
                retryable=False,
                status_code=status
            )
        elif status in (400, 422):
            raise ConnectorException(
                code=ErrorCode.PLATFORM_CONTENT_REJECTED,
                message=f"Lemmy rejected post: {text}",
                retryable=False,
                status_code=status
            )
        elif status == 429:
            retry_after = resp.headers.get("Retry-After", "5")
            raise ConnectorException(
                code=ErrorCode.PLATFORM_RATE_LIMIT,
                message=f"Lemmy rate limit hit. Retry after {retry_after}s",
                retryable=True,
                details={"retry_after": int(retry_after) if retry_after.isdigit() else 5},
                status_code=status
            )
        elif status >= 500:
            raise ConnectorException(
                code=ErrorCode.PLATFORM_UNAVAILABLE,
                message=f"Lemmy server error ({status}): {text}",
                retryable=True,
                status_code=status
            )
        else:
            raise ConnectorException(
                code=ErrorCode.DEST_SPEC_VIOLATION,
                message=f"Lemmy error ({status}): {text}",
                retryable=False,
                status_code=status
            )
