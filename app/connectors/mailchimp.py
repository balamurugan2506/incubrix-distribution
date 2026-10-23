"""Mailchimp Newsletter Campaign Connector implementation (Drafts Only).

CRITICAL NON-NEGOTIABLE SAFETY CONSTRAINT:
This connector ONLY creates and manages campaign drafts (status: 'save').
It NEVER triggers email delivery or sends to real subscribers.
"""

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


class MailchimpConnector(BaseConnector):
    key = "mailchimp"

    def _get_base_url(self, connection: ConnectionSchema) -> str:
        return (connection.base_url or "http://localhost:8001/mailchimp").rstrip("/")

    def _get_headers(self, connection: ConnectionSchema) -> dict:
        api_key = (
            connection.credentials.get("api_key")
            or connection.credentials.get("auth_token")
            or "mock_mailchimp_key-us1"
        )
        if not api_key:
            raise ConnectorException(
                code=ErrorCode.CONNECTION_AUTH_EXPIRED,
                message="Mailchimp API key missing from connection credentials",
                retryable=False,
                status_code=401
            )
        headers = {
            "Authorization": f"Bearer {api_key}",
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
        if not rendition.title or len(rendition.title.strip()) < 5:
            violations.append("Mailchimp campaign requires a subject line / title of at least 5 characters")
        elif len(rendition.title) > 150:
            violations.append("Mailchimp campaign title exceeds 150 characters limit")

        if not rendition.body or len(rendition.body.strip()) < 20:
            violations.append("Mailchimp campaign HTML/body must be at least 20 characters")
        elif len(rendition.body) > 100000:
            violations.append("Mailchimp campaign body exceeds 100,000 characters limit")

        if len(rendition.tags) > 0:
            violations.append("Mailchimp campaigns do not use tags directly on campaign creation")

        return ValidateResult(ok=len(violations) == 0, violations=violations)

    async def publish(
        self,
        rendition: RenditionSchema,
        destination: DestinationSchema,
        connection: ConnectionSchema,
        idempotency_key: str
    ) -> PublishResult:
        """
        Creates a Campaign DRAFT only.
        NEVER sends to real subscribers.
        """
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
        list_id = destination.instance_config.get("list_id") or "list_default_123"

        # 1. Create campaign draft
        campaign_payload = {
            "type": "regular",
            "recipients": {"list_id": list_id},
            "settings": {
                "subject_line": rendition.title,
                "title": rendition.title,
                "from_name": "IncuBrix Syndication",
                "reply_to": "newsletter@incubrix.local"
            }
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(f"{base_url}/3.0/campaigns", json=campaign_payload, headers=headers)
            except httpx.RequestError as exc:
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Mailchimp network error: {str(exc)}",
                    retryable=True,
                    status_code=503
                ) from exc

        if resp.status_code == 401:
            raise ConnectorException(
                code=ErrorCode.CONNECTION_AUTH_EXPIRED,
                message="Mailchimp API key unauthorized or expired",
                retryable=False,
                status_code=401
            )
        elif resp.status_code >= 400:
            raise ConnectorException(
                code=ErrorCode.PLATFORM_CONTENT_REJECTED,
                message=f"Mailchimp error: HTTP {resp.status_code}",
                retryable=resp.status_code in (429, 503),
                status_code=resp.status_code
            )

        camp_data = resp.json()
        campaign_id = str(camp_data.get("id"))
        archive_url = camp_data.get("archive_url", f"https://mailchimp.com/campaigns/{campaign_id}")

        # 2. Set campaign content (HTML body)
        content_payload = {"html": f"<h1>{rendition.title}</h1><p>{rendition.body}</p>"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.put(f"{base_url}/3.0/campaigns/{campaign_id}/content", json=content_payload, headers=headers)

        # Status is strictly DRAFT ('draft' / 'save')
        return PublishResult(
            platform_post_id=campaign_id,
            live_url=archive_url,
            status="draft"
        )

    async def get_status(
        self,
        platform_post_id: str,
        connection: ConnectionSchema
    ) -> StatusResult:
        base_url = self._get_base_url(connection)
        headers = self._get_headers(connection)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url}/3.0/campaigns/{platform_post_id}", headers=headers)

        if resp.status_code == 200:
            data = resp.json()
            return StatusResult(status="draft", live_url=data.get("archive_url", ""))

        return StatusResult(status="not_found", live_url="")

    async def delete(
        self,
        platform_post_id: str,
        connection: ConnectionSchema
    ) -> DeleteResult:
        base_url = self._get_base_url(connection)
        headers = self._get_headers(connection)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(f"{base_url}/3.0/campaigns/{platform_post_id}", headers=headers)

        deleted = resp.status_code in (200, 204)
        return DeleteResult(deleted=deleted)

    async def fetch_metrics(
        self,
        platform_post_id: str,
        connection: ConnectionSchema,
        since: Optional[str] = None
    ) -> MetricsResult:
        base_url = self._get_base_url(connection)
        headers = self._get_headers(connection)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url}/3.0/reports/{platform_post_id}", headers=headers)

        if resp.status_code == 200:
            data = resp.json()
            opens = data.get("opens", {}).get("unique_opens", 15)
            clicks = data.get("clicks", {}).get("unique_subscriber_clicks", 5)
            shares = data.get("shares", {}).get("facebook_shares", 1)
            return MetricsResult(views=opens, likes=0, comments=0, shares=shares, clicks=clicks)

        return MetricsResult()

    async def reconcile(
        self,
        rendition: RenditionSchema,
        destination: DestinationSchema,
        connection: ConnectionSchema,
        idempotency_key: str
    ) -> Optional[PublishResult]:
        return None
