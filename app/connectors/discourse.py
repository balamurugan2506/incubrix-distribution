"""Discourse Forum API Connector."""

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


class DiscourseConnector(BaseConnector):
    key = "discourse"

    def _get_base_url(self, connection: ConnectionSchema) -> str:
        return (connection.base_url or settings.DISCOURSE_BASE_URL).rstrip("/")

    def _get_headers(self, connection: ConnectionSchema) -> dict:
        api_key = connection.credentials.get("api_key") or settings.DISCOURSE_API_KEY
        api_username = connection.credentials.get("api_username") or settings.DISCOURSE_API_USERNAME
        if not api_key or not api_username:
            raise ConnectorException(
                code=ErrorCode.CONNECTION_AUTH_EXPIRED,
                message="Discourse API-Key and API-Username are required",
                retryable=False,
                status_code=401
            )
        headers = {
            "Api-Key": api_key,
            "Api-Username": api_username,
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

        if not rendition.title or len(rendition.title.strip()) < 15:
            violations.append("Discourse topic title must be at least 15 characters")
        elif len(rendition.title) > 255:
            violations.append("Discourse topic title cannot exceed 255 characters")

        if not rendition.body or len(rendition.body.strip()) < 20:
            violations.append("Discourse post body must be at least 20 characters")
        elif len(rendition.body) > 65535:
            violations.append("Discourse post body exceeds maximum allowed 65,535 characters")

        category_id = destination.instance_config.get("category_id")
        topic_id = destination.instance_config.get("topic_id")
        if not category_id and not topic_id:
            violations.append("Discourse requires either a category_id (new topic) or topic_id (reply)")

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
                message=f"Discourse validation failed: {'; '.join(val.violations)}",
                retryable=False,
                details={"violations": val.violations},
                status_code=422
            )

        base_url = self._get_base_url(connection)
        headers = self._get_headers(connection)
        headers["Idempotency-Key"] = idempotency_key

        payload = {
            "title": rendition.title,
            "raw": rendition.body,
        }
        if destination.instance_config.get("category_id"):
            payload["category"] = destination.instance_config["category_id"]
        if destination.instance_config.get("topic_id"):
            payload["topic_id"] = destination.instance_config["topic_id"]
        if rendition.tags:
            payload["tags"] = rendition.tags[:5]

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(f"{base_url}/posts.json", json=payload, headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Discourse platform connection error: {str(exc)}",
                    retryable=True,
                    status_code=503
                )

        if resp.status_code in (200, 201):
            data = resp.json()
            post_id = str(data.get("id"))
            topic_id = data.get("topic_id")
            topic_slug = data.get("topic_slug", "topic")
            post_number = data.get("post_number", 1)
            live_url = f"{base_url}/t/{topic_slug}/{topic_id}/{post_number}"
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
        """Look up existing Discourse post by title/raw after timeout/unknown outcome."""
        base_url = self._get_base_url(connection)
        headers = self._get_headers(connection)
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(f"{base_url}/search.json?q={rendition.title}", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    posts = data.get("posts", [])
                    for p in posts:
                        if rendition.title in str(p.get("title", "")) or rendition.title in str(p.get("raw", "")):
                            post_id = str(p.get("id"))
                            topic_id = p.get("topic_id")
                            topic_slug = p.get("topic_slug", "topic")
                            post_number = p.get("post_number", 1)
                            live_url = f"{base_url}/t/{topic_slug}/{topic_id}/{post_number}"
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
                resp = await client.get(f"{base_url}/posts/{platform_post_id}.json", headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Failed to connect to Discourse: {str(exc)}",
                    retryable=True,
                    status_code=503
                )

        if resp.status_code == 200:
            data = resp.json()
            topic_id = data.get("topic_id")
            topic_slug = data.get("topic_slug", "topic")
            post_num = data.get("post_number", 1)
            return StatusResult(
                status="published",
                live_url=f"{base_url}/t/{topic_slug}/{topic_id}/{post_num}"
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
                resp = await client.delete(f"{base_url}/posts/{platform_post_id}.json", headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Discourse delete request failed: {str(exc)}",
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
                resp = await client.get(f"{base_url}/posts/{platform_post_id}.json", headers=headers)
            except httpx.RequestError:
                return MetricsResult()

        if resp.status_code == 200:
            data = resp.json()
            return MetricsResult(
                views=int(data.get("reads", 0)),
                likes=int(data.get("like_count", 0)),
                comments=int(data.get("reply_count", 0)),
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
                message=f"Discourse authorization failed: {text}",
                retryable=False,
                status_code=status
            )
        elif status == 422:
            raise ConnectorException(
                code=ErrorCode.PLATFORM_CONTENT_REJECTED,
                message=f"Discourse rejected content: {text}",
                retryable=False,
                status_code=status
            )
        elif status == 429:
            retry_after = resp.headers.get("Retry-After", "5")
            raise ConnectorException(
                code=ErrorCode.PLATFORM_RATE_LIMIT,
                message=f"Discourse rate limit. Retry after {retry_after}s",
                retryable=True,
                details={"retry_after": int(retry_after) if retry_after.isdigit() else 5},
                status_code=status
            )
        elif status >= 500:
            raise ConnectorException(
                code=ErrorCode.PLATFORM_UNAVAILABLE,
                message=f"Discourse unavailable ({status}): {text}",
                retryable=True,
                status_code=status
            )
        else:
            raise ConnectorException(
                code=ErrorCode.DEST_SPEC_VIOLATION,
                message=f"Discourse error ({status}): {text}",
                retryable=False,
                status_code=status
            )
