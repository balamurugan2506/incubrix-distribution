"""Ghost Admin API Connector."""

import time
import jwt
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


class GhostConnector(BaseConnector):
    key = "ghost"

    def _get_base_url(self, connection: ConnectionSchema) -> str:
        return (connection.base_url or settings.get_ghost_base_url()).rstrip("/")

    def _generate_ghost_token(self, connection: ConnectionSchema) -> str:
        raw_key = connection.credentials.get("admin_api_key") or settings.get_ghost_api_key()
        if not raw_key:
            raise ConnectorException(
                code=ErrorCode.CONNECTION_AUTH_EXPIRED,
                message="Ghost Admin API key missing",
                retryable=False,
                status_code=401
            )

        if ":" in raw_key:
            try:
                key_id, secret_hex = raw_key.split(":")
                iat = int(time.time())
                exp = iat + 300
                token = jwt.encode(
                    payload={"iat": iat, "exp": exp, "aud": "/admin/"},
                    key=bytes.fromhex(secret_hex),
                    algorithm="HS256",
                    headers={"kid": key_id}
                )
                return token
            except Exception:
                return raw_key  # Fallback for mock simulation keys
        return raw_key

    def _get_headers(self, connection: ConnectionSchema) -> dict:
        token = self._generate_ghost_token(connection)
        headers = {
            "Authorization": f"Ghost {token}",
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

        if not rendition.title or len(rendition.title.strip()) < 1:
            violations.append("Ghost post title is required")
        elif len(rendition.title) > 255:
            violations.append("Ghost post title cannot exceed 255 characters")

        if not rendition.body or len(rendition.body.strip()) < 10:
            violations.append("Ghost post body must contain at least 10 characters")
        elif len(rendition.body) > 500000:
            violations.append("Ghost post body exceeds 500,000 character limit")

        if len(rendition.tags) > 15:
            violations.append("Ghost allows a maximum of 15 tags")

        return ValidateResult(ok=len(violations) == 0, violations=violations)

    def _admin_endpoint(self, base_url: str, path: str) -> str:
        clean_path = path.lstrip("/")
        if base_url.endswith("/ghost"):
            return f"{base_url}/api/admin/{clean_path}"
        return f"{base_url}/ghost/api/admin/{clean_path}"

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
                message=f"Ghost validation failed: {'; '.join(val.violations)}",
                retryable=False,
                details={"violations": val.violations},
                status_code=422
            )

        base_url = self._get_base_url(connection)
        headers = self._get_headers(connection)
        headers["Idempotency-Key"] = idempotency_key

        html_content = rendition.body if "<p>" in rendition.body else f"<p>{rendition.body}</p>"

        post_data = {
            "title": rendition.title,
            "html": html_content,
            "status": "published",
            "tags": [{"name": t} for t in rendition.tags[:15]],
            "custom_excerpt": rendition.summary,
            "canonical_url": rendition.canonical_url
        }

        payload = {"posts": [post_data]}
        endpoint = self._admin_endpoint(base_url, "posts/?source=html")

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(endpoint, json=payload, headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Ghost platform connection error: {str(exc)}",
                    retryable=True,
                    status_code=503
                )

        if resp.status_code in (200, 201):
            data = resp.json()
            post = data.get("posts", [{}])[0]
            post_id = str(post.get("id"))
            live_url = post.get("url") or f"{base_url}/{post_id}/"
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
        """Look up existing Ghost post by title after timeout/unknown outcome."""
        base_url = self._get_base_url(connection)
        headers = self._get_headers(connection)
        endpoint = self._admin_endpoint(base_url, f"posts/?filter=title:'{rendition.title}'")
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(endpoint, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    posts = data.get("posts", [])
                    for p in posts:
                        if p.get("title") == rendition.title:
                            post_id = str(p.get("id"))
                            live_url = p.get("url") or f"{base_url}/{p.get('slug', post_id)}"
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
        endpoint = self._admin_endpoint(base_url, f"posts/{platform_post_id}/")

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(endpoint, headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Failed to fetch Ghost post status: {str(exc)}",
                    retryable=True,
                    status_code=503
                )

        if resp.status_code == 200:
            post = resp.json().get("posts", [{}])[0]
            return StatusResult(
                status="published",
                live_url=post.get("url") or f"{base_url}/{platform_post_id}/"
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
        endpoint = self._admin_endpoint(base_url, f"posts/{platform_post_id}/")

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.delete(endpoint, headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Ghost delete failed: {str(exc)}",
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
                message=f"Ghost authentication failed: {text}",
                retryable=False,
                status_code=status
            )
        elif status == 422:
            raise ConnectorException(
                code=ErrorCode.PLATFORM_CONTENT_REJECTED,
                message=f"Ghost content validation error: {text}",
                retryable=False,
                status_code=status
            )
        elif status == 429:
            retry_after = resp.headers.get("Retry-After", "5")
            raise ConnectorException(
                code=ErrorCode.PLATFORM_RATE_LIMIT,
                message=f"Ghost rate limit reached. Retry after {retry_after}s",
                retryable=True,
                details={"retry_after": int(retry_after) if retry_after.isdigit() else 5},
                status_code=status
            )
        elif status >= 500:
            raise ConnectorException(
                code=ErrorCode.PLATFORM_UNAVAILABLE,
                message=f"Ghost platform unavailable ({status}): {text}",
                retryable=True,
                status_code=status
            )
        else:
            raise ConnectorException(
                code=ErrorCode.DEST_SPEC_VIOLATION,
                message=f"Ghost error ({status}): {text}",
                retryable=False,
                status_code=status
            )
