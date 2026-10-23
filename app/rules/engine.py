"""Posting-Rules Validation Engine enforcing destination and platform safety policies."""

import re
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.destination import DestinationModel
from app.models.publication import PublicationRecordModel
from app.schemas.connector import RenditionSchema, DestinationSchema
from app.rules.errors import ConnectorException, ErrorCode
from app.connectors.registry import registry


class PostingRulesEngine:
    """Enforces frequency caps, self-promo, link policy, AI disclosures, and format limits."""

    @staticmethod
    def _extract_links(text: str) -> List[str]:
        """Extract URLs from markdown or text."""
        url_pattern = r'https?://[^\s)\]">]+'
        return re.findall(url_pattern, text or "")

    @staticmethod
    def _is_self_promotional(rendition: RenditionSchema) -> bool:
        """Detect obvious promotional keywords and marketing CTA."""
        promo_keywords = [
            "buy now", "discount", "limited offer", "coupon",
            "sign up today", "pricing plan", "affiliate link",
            "special deal", "use promo code"
        ]
        text = f"{rendition.title or ''} {rendition.body or ''} {rendition.summary or ''}".lower()
        return any(kw in text for kw in promo_keywords)

    async def check_rules(
        self,
        rendition: RenditionSchema,
        destination: DestinationModel,
        db: Optional[AsyncSession] = None,
        is_automated_request: bool = True
    ) -> List[str]:
        """
        Validate all posting rules against the rendition and destination.
        Raises ConnectorException for blocking violations, or returns warnings list.
        """
        # 1. Destination Enabled Check
        if destination.enabled is False:
            raise ConnectorException(
                code=ErrorCode.CONNECTOR_DISABLED,
                message=f"Destination '{destination.name}' is currently disabled in the catalogue.",
                retryable=False,
                status_code=400
            )

        # 2. Automation Allowance Check
        if is_automated_request and destination.automation_allowed is False:
            raise ConnectorException(
                code=ErrorCode.CONNECTOR_DISABLED,
                message=(
                    f"Destination '{destination.name}' prohibits automated posting. "
                    "Use assisted publishing workflow instead."
                ),
                retryable=False,
                status_code=400
            )

        # 3. Frequency Cap Check
        if db is not None and destination.frequency_cap and destination.frequency_cap > 0:
            since = datetime.now(timezone.utc) - timedelta(hours=24)
            stmt = select(func.count(PublicationRecordModel.id)).where(
                PublicationRecordModel.destination_id == destination.id,
                PublicationRecordModel.created_at >= since,
                PublicationRecordModel.status.in_(["published", "queued", "running"])
            )
            res = await db.execute(stmt)
            recent_count = res.scalar() or 0
            if recent_count >= destination.frequency_cap:
                raise ConnectorException(
                    code=ErrorCode.DEST_RULE_FREQUENCY_CAP,
                    message=(
                        f"Frequency cap exceeded for destination '{destination.name}': "
                        f"{recent_count}/{destination.frequency_cap} posts published in the last 24h."
                    ),
                    retryable=True,
                    details={"recent_count": recent_count, "cap": destination.frequency_cap},
                    status_code=429
                )

        # 4. Self-Promotion Policy
        if not destination.self_promo_allowed and self._is_self_promotional(rendition):
            raise ConnectorException(
                code=ErrorCode.DEST_SPEC_VIOLATION,
                message=f"Destination '{destination.name}' prohibits self-promotional content.",
                retryable=False,
                status_code=422
            )

        # 5. Link Policy
        links = self._extract_links(rendition.body)
        if destination.link_policy == "none" and len(links) > 0:
            raise ConnectorException(
                code=ErrorCode.DEST_SPEC_VIOLATION,
                message=f"Destination '{destination.name}' strictly prohibits external links (found {len(links)} link(s)).",
                retryable=False,
                details={"links_found": links},
                status_code=422
            )
        elif destination.link_policy == "restricted" and len(links) > 2:
            raise ConnectorException(
                code=ErrorCode.DEST_SPEC_VIOLATION,
                message=f"Destination '{destination.name}' allows at most 2 external links (found {len(links)} link(s)).",
                retryable=False,
                details={"links_found": links},
                status_code=422
            )

        # 6. AI-Content Disclosure Policy
        if destination.disclosure_required and rendition.is_ai_generated:
            if not rendition.ai_disclosure_text or len(rendition.ai_disclosure_text.strip()) == 0:
                raise ConnectorException(
                    code=ErrorCode.DEST_SPEC_VIOLATION,
                    message=(
                        f"Destination '{destination.name}' requires explicit AI-content disclosure statement "
                        "for AI-generated renditions."
                    ),
                    retryable=False,
                    status_code=422
                )

        # 7. Connector Manifest Limits Validation
        try:
            manifest = registry.get_manifest(destination.connector_key)
            fl = manifest.format_limits

            # Title limits
            title_len = len(rendition.title.strip()) if rendition.title else 0
            if title_len < fl.title_min_chars:
                raise ConnectorException(
                    code=ErrorCode.DEST_SPEC_VIOLATION,
                    message=f"Title is too short for {destination.connector_key} (min {fl.title_min_chars} chars)",
                    retryable=False,
                    status_code=422
                )
            if title_len > fl.title_max_chars:
                raise ConnectorException(
                    code=ErrorCode.DEST_SPEC_VIOLATION,
                    message=f"Title exceeds {destination.connector_key} limit (max {fl.title_max_chars} chars)",
                    retryable=False,
                    status_code=422
                )

            # Body limits
            body_len = len(rendition.body.strip()) if rendition.body else 0
            if body_len < fl.body_min_chars:
                raise ConnectorException(
                    code=ErrorCode.DEST_SPEC_VIOLATION,
                    message=f"Body is too short for {destination.connector_key} (min {fl.body_min_chars} chars)",
                    retryable=False,
                    status_code=422
                )
            if body_len > fl.body_max_chars:
                raise ConnectorException(
                    code=ErrorCode.DEST_SPEC_VIOLATION,
                    message=f"Body exceeds {destination.connector_key} limit (max {fl.body_max_chars} chars)",
                    retryable=False,
                    status_code=422
                )

            # Tag limits
            if len(rendition.tags) > fl.max_tags:
                raise ConnectorException(
                    code=ErrorCode.DEST_SPEC_VIOLATION,
                    message=f"Too many tags for {destination.connector_key} (max {fl.max_tags})",
                    retryable=False,
                    status_code=422
                )
        except Exception as e:
            if isinstance(e, ConnectorException):
                raise e

        return []


rules_engine = PostingRulesEngine()
