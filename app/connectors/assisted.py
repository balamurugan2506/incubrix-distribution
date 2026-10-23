"""Assisted Publishing Connector for destinations prohibiting automated posting."""

from typing import List, Optional
from app.connectors.base import BaseConnector
from app.schemas.connector import (
    RenditionSchema,
    DestinationSchema,
    ConnectionSchema,
    ValidateResult,
    PublishResult,
    StatusResult,
    DeleteResult,
    AssistPackResult
)
from app.rules.errors import ConnectorException, ErrorCode


class AssistedConnector(BaseConnector):
    key = "assisted"

    async def validate(
        self,
        rendition: RenditionSchema,
        destination: DestinationSchema,
        connection: ConnectionSchema
    ) -> ValidateResult:
        violations: List[str] = []

        if not rendition.body and not rendition.title:
            violations.append("Assisted publishing pack requires at least a title or body text")

        submission_url = destination.instance_config.get("submission_url") or destination.url
        if not submission_url:
            violations.append("Destination submission URL is missing for assisted publishing")

        return ValidateResult(ok=len(violations) == 0, violations=violations)

    async def publish(
        self,
        rendition: RenditionSchema,
        destination: DestinationSchema,
        connection: ConnectionSchema,
        idempotency_key: str
    ) -> PublishResult:
        # Automated publishing is strictly prohibited for assisted destinations
        raise ConnectorException(
            code=ErrorCode.CONNECTOR_DISABLED,
            message=(
                f"Automated publishing is not permitted on destination '{destination.name}'. "
                "Use build_assist_pack to generate human-submission assets."
            ),
            retryable=False,
            status_code=400,
            details={"destination": destination.name, "url": destination.url}
        )

    async def get_status(
        self,
        platform_post_id: str,
        connection: ConnectionSchema
    ) -> StatusResult:
        return StatusResult(
            status="manual_review",
            live_url=""
        )

    async def delete(
        self,
        platform_post_id: str,
        connection: ConnectionSchema
    ) -> DeleteResult:
        raise ConnectorException(
            code=ErrorCode.DEST_SPEC_VIOLATION,
            message="Deletion is not automated for assisted-mode destinations. Please remove manually.",
            retryable=False,
            status_code=400
        )

    async def build_assist_pack(
        self,
        rendition: RenditionSchema,
        destination: DestinationSchema
    ) -> AssistPackResult:
        submission_url = destination.instance_config.get("submission_url") or destination.url

        # Format ready-to-copy caption
        caption_parts = []
        if rendition.title:
            caption_parts.append(rendition.title)
        if rendition.summary:
            caption_parts.append(rendition.summary)
        caption_parts.append(rendition.body)

        if rendition.tags:
            tag_str = " ".join([f"#{t.lstrip('#')}" for t in rendition.tags])
            caption_parts.append(tag_str)

        if rendition.is_ai_generated and rendition.ai_disclosure_text:
            caption_parts.append(f"AI Disclosure: {rendition.ai_disclosure_text}")

        caption = "\n\n".join(caption_parts)

        # Build human checklist
        checklist = [
            f"1. Navigate to destination submission page: {submission_url}",
            "2. Ensure you are signed in with the authorized account",
            "3. Paste the formatted caption into the post editor",
            f"4. Attach media files ({len(rendition.media_urls)} asset(s))",
            "5. Verify destination rules & guidelines before clicking submit",
            "6. After submission, update IncuBrix job with the live post URL"
        ]

        return AssistPackResult(
            files=rendition.media_urls,
            caption=caption,
            deep_link=submission_url,
            checklist=checklist
        )
