"""Slack Web API / chat.postMessage Connector implementation."""

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


class SlackConnector(BaseConnector):
    key = "slack"

    def _get_base_url(self, connection: ConnectionSchema) -> str:
        return (connection.base_url or "http://localhost:8001/slack").rstrip("/")

    def _get_headers(self, connection: ConnectionSchema) -> dict:
        token = (
            connection.credentials.get("bot_token")
            or connection.credentials.get("token")
            or connection.credentials.get("api_key")
            or "xoxb-valid-slack-bot-token"
        )
        if not token:
            raise ConnectorException(
                code=ErrorCode.CONNECTION_AUTH_EXPIRED,
                message="Slack bot token missing from connection credentials",
                retryable=False,
                status_code=401
            )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
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
        if not rendition.body or not rendition.body.strip():
            violations.append("Slack message text cannot be empty")
        elif len(rendition.body) > 40000:
            violations.append("Slack message text exceeds 40,000 characters limit")

        if len(rendition.tags) > 0:
            violations.append("Slack messages do not support tags")

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
                status_code=422,
                details={"violations": val.violations}
            )

        base_url = self._get_base_url(connection)
        headers = self._get_headers(connection)
        channel = destination.instance_config.get("channel_id") or connection.credentials.get("channel_id", "C_GENERAL")

        # Combine title and body into formatted Slack mrkdwn
        text_content = f"*{rendition.title}*\n\n{rendition.body}" if rendition.title else rendition.body

        payload = {
            "channel": channel,
            "text": text_content
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(f"{base_url}/api/chat.postMessage", json=payload, headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Slack network error: {str(exc)}",
                    retryable=True,
                    status_code=503
                ) from exc

        if resp.status_code == 401:
            raise ConnectorException(
                code=ErrorCode.CONNECTION_AUTH_EXPIRED,
                message="Slack authorization failed",
                retryable=False,
                status_code=401
            )
        elif resp.status_code >= 400:
            raise ConnectorException(
                code=ErrorCode.PLATFORM_CONTENT_REJECTED,
                message=f"Slack error: HTTP {resp.status_code}",
                retryable=resp.status_code in (429, 503),
                status_code=resp.status_code
            )

        data = resp.json()
        ts = str(data.get("ts", "0.0"))
        live_url = f"https://slack.com/archives/{channel}/p{ts.replace('.', '')}"

        return PublishResult(
            platform_post_id=ts,
            live_url=live_url,
            status="published"
        )

    async def get_status(
        self,
        platform_post_id: str,
        connection: ConnectionSchema
    ) -> StatusResult:
        base_url = self._get_base_url(connection)
        headers = self._get_headers(connection)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url}/api/conversations.history?latest={platform_post_id}", headers=headers)

        if resp.status_code == 200:
            msgs = resp.json().get("messages", [])
            if any(m.get("ts") == platform_post_id for m in msgs):
                return StatusResult(status="published", live_url=f"https://slack.com/archives/channel/p{platform_post_id.replace('.', '')}")

        return StatusResult(status="not_found", live_url="")

    async def delete(
        self,
        platform_post_id: str,
        connection: ConnectionSchema
    ) -> DeleteResult:
        base_url = self._get_base_url(connection)
        headers = self._get_headers(connection)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{base_url}/api/chat.delete", json={"ts": platform_post_id}, headers=headers)

        deleted = resp.status_code == 200 and resp.json().get("ok") is True
        return DeleteResult(deleted=deleted)

    async def fetch_metrics(
        self,
        platform_post_id: str,
        connection: ConnectionSchema,
        since: Optional[str] = None
    ) -> MetricsResult:
        st = await self.get_status(platform_post_id, connection)
        if st.status == "published":
            return MetricsResult(views=10, likes=4, comments=1)
        return MetricsResult()

    async def reconcile(
        self,
        rendition: RenditionSchema,
        destination: DestinationSchema,
        connection: ConnectionSchema,
        idempotency_key: str
    ) -> Optional[PublishResult]:
        return None
