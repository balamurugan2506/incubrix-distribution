"""Dev.to / Forem API Connector implementation."""

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


class DevtoConnector(BaseConnector):
    key = "devto"

    def _get_base_url(self, connection: ConnectionSchema) -> str:
        return (connection.base_url or settings.DEVTO_BASE_URL).rstrip("/")

    def _get_headers(self, connection: ConnectionSchema) -> dict:
        api_key = connection.credentials.get("api_key") or settings.DEVTO_API_KEY
        if not api_key:
            raise ConnectorException(
                code=ErrorCode.CONNECTION_AUTH_EXPIRED,
                message="Dev.to API key missing from connection credentials",
                retryable=False,
                status_code=401
            )
        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if connection.metadata.get("simulate"):
            headers["x-simulate"] = str(connection.metadata["simulate"])
        return headers

    async def validate(
        self,
        rendition: RenditionSchema,
        destination: DestinationSchema,
        connection: ConnectionSchema
    ) -> ValidateResult:
        violations: List[str] = []

        if not rendition.title or len(rendition.title.strip()) < 5:
            violations.append("Dev.to requires a title of at least 5 characters")
        elif len(rendition.title) > 128:
            violations.append("Dev.to title cannot exceed 128 characters")

        if not rendition.body or len(rendition.body.strip()) < 30:
            violations.append("Dev.to article body must be at least 30 characters")
        elif len(rendition.body) > 100000:
            violations.append("Dev.to article body exceeds 100,000 characters limit")

        if len(rendition.tags) > 4:
            violations.append("Dev.to allows a maximum of 4 tags")

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
                message=f"Validation failed: {'; '.join(val.violations)}",
                retryable=False,
                details={"violations": val.violations},
                status_code=422
            )

        base_url = self._get_base_url(connection)
        headers = self._get_headers(connection)
        headers["Idempotency-Key"] = idempotency_key

        payload = {
            "article": {
                "title": rendition.title,
                "body_markdown": rendition.body,
                "published": True,
                "tags": [tag.replace("#", "").replace(" ", "") for tag in rendition.tags[:4]],
                "canonical_url": rendition.canonical_url,
                "description": rendition.summary
            }
        }

        # Optional organization ID from destination instance config
        if destination.instance_config.get("organization_id"):
            payload["article"]["organization_id"] = destination.instance_config["organization_id"]
        if destination.instance_config.get("series"):
            payload["article"]["series"] = destination.instance_config["series"]

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(f"{base_url}/api/articles", json=payload, headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Failed to connect to Dev.to platform: {str(exc)}",
                    retryable=True,
                    status_code=503
                )

        if resp.status_code in (200, 201):
            data = resp.json()
            post_id = str(data.get("id"))
            live_url = data.get("url") or f"{base_url}/{data.get('path', post_id)}"
            return PublishResult(
                platform_post_id=post_id,
                live_url=live_url,
                status="published"
            )

        self._handle_http_error(resp)

    async def reconcile(
        self,
        rendition: RenditionSchema,
        destination: DestinationSchema,
        connection: ConnectionSchema,
        idempotency_key: str
    ) -> Optional[PublishResult]:
        """Look up existing Dev.to article by title after a timeout/unknown outcome."""
        base_url = self._get_base_url(connection)
        headers = self._get_headers(connection)
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(f"{base_url}/api/articles?title={rendition.title}", headers=headers)
                if resp.status_code == 200:
                    articles = resp.json()
                    if isinstance(articles, list):
                        for art in articles:
                            if art.get("title") == rendition.title:
                                post_id = str(art.get("id"))
                                live_url = art.get("url") or f"{base_url}/{art.get('path', post_id)}"
                                return PublishResult(
                                    platform_post_id=post_id,
                                    live_url=live_url,
                                    status="published"
                                )
            except Exception:
                return None
        return None

    async def get_status(
        self,
        platform_post_id: str,
        connection: ConnectionSchema
    ) -> StatusResult:
        base_url = self._get_base_url(connection)
        headers = self._get_headers(connection)

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(f"{base_url}/api/articles/{platform_post_id}", headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Failed to connect to Dev.to platform: {str(exc)}",
                    retryable=True,
                    status_code=503
                )

        if resp.status_code == 200:
            data = resp.json()
            return StatusResult(
                status="published",
                live_url=data.get("url") or f"{base_url}/articles/{platform_post_id}"
            )
        elif resp.status_code == 404:
            return StatusResult(status="not_found", live_url="")

        self._handle_http_error(resp)

    async def delete(
        self,
        platform_post_id: str,
        connection: ConnectionSchema
    ) -> DeleteResult:
        base_url = self._get_base_url(connection)
        headers = self._get_headers(connection)

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.delete(f"{base_url}/api/articles/{platform_post_id}", headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Failed to connect to Dev.to platform: {str(exc)}",
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
        headers = self._get_headers(connection)

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(f"{base_url}/api/articles/{platform_post_id}", headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Failed to connect to Dev.to: {str(exc)}",
                    retryable=True,
                    status_code=503
                )

        if resp.status_code == 200:
            data = resp.json()
            return MetricsResult(
                views=int(data.get("page_views_count", 0)),
                likes=int(data.get("public_reactions_count", 0)),
                comments=int(data.get("comments_count", 0)),
                shares=0,
                saves=int(data.get("reading_list_count", 0)),
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
                message=f"Dev.to authentication failed or expired: {text}",
                retryable=False,
                status_code=status
            )
        elif status == 422:
            raise ConnectorException(
                code=ErrorCode.PLATFORM_CONTENT_REJECTED,
                message=f"Dev.to rejected post content: {text}",
                retryable=False,
                status_code=status
            )
        elif status == 429:
            retry_after = resp.headers.get("Retry-After", "5")
            raise ConnectorException(
                code=ErrorCode.PLATFORM_RATE_LIMIT,
                message=f"Dev.to rate limit encountered. Retry after {retry_after}s",
                retryable=True,
                details={"retry_after": int(retry_after) if retry_after.isdigit() else 5},
                status_code=status
            )
        elif status >= 500:
            raise ConnectorException(
                code=ErrorCode.PLATFORM_UNAVAILABLE,
                message=f"Dev.to platform error ({status}): {text}",
                retryable=True,
                status_code=status
            )
        else:
            raise ConnectorException(
                code=ErrorCode.DEST_SPEC_VIOLATION,
                message=f"Dev.to unexpected error ({status}): {text}",
                retryable=False,
                status_code=status
            )
