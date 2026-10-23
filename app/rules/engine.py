"""Posting-Rules Validation Engine enforcing destination and platform safety policies."""

import re
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple, Any, Dict
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
        """
        Extract links in every written form:
        - http:// and https:// URLs
        - www. prefixed addresses
        - Markdown links [text](url)
        - HTML links <a href="...">
        - Bare domains (e.g. incubrix.ai, github.com, example.org)
        """
        if not text:
            return []

        found_links = set()

        # 1. HTML href links: <a ... href="..." ...>
        html_hrefs = re.findall(r'<a\s+(?:[^>]*?\s+)?href=["\']([^"\']+)["\']', text, re.IGNORECASE)
        for h in html_hrefs:
            clean = h.strip()
            if clean and not clean.startswith("#"):
                found_links.add(clean)

        # 2. Markdown links: [anchor](url)
        md_links = re.findall(r'\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)', text)
        for _, u in md_links:
            clean = u.strip()
            if clean and not clean.startswith("#"):
                found_links.add(clean)

        # 3. Explicit HTTP/HTTPS URLs
        explicit_urls = re.findall(r'https?://[^\s)\]">]+', text, re.IGNORECASE)
        for u in explicit_urls:
            found_links.add(u.rstrip('.,;!?:'))

        # 4. www. addresses without scheme
        www_links = re.findall(r'\bwww\.[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+[^\s)\]">]*', text, re.IGNORECASE)
        for w in www_links:
            found_links.add(w.rstrip('.,;!?:'))

        # 5. Bare domains with common TLDs (e.g. incubrix.ai, example.com, test.org)
        tlds = r'(?:com|org|net|edu|gov|io|ai|co|dev|app|info|biz|me|tech|xyz|so|fm|tv|online)'
        bare_domains = re.findall(rf'\b[a-zA-Z0-9](?:[a-zA-Z0-9-]{{0,61}}[a-zA-Z0-9])?\.' + tlds + rf'(?:/[^\s)\]">]*)?', text, re.IGNORECASE)
        for bd in bare_domains:
            # Avoid adding fragment of already captured explicit URL
            bd_clean = bd.rstrip('.,;!?:')
            if not any(bd_clean in existing for existing in found_links):
                found_links.add(bd_clean)

        return list(found_links)

    @staticmethod
    def _is_self_promotional(rendition: RenditionSchema) -> Tuple[bool, List[str]]:
        """
        Detect self-promotional content using multi-marker heuristics.
        Returns (is_promo, matched_markers).
        Requires at least 2 distinct marker categories to avoid false positives,
        OR any single strong commercial keyword.
        """
        text = f"{rendition.title or ''} {rendition.body or ''} {rendition.summary or ''}".lower()

        # Strong standalone commercial keywords
        strong_markers = [
            "affiliate link", "affiliate code", "referral link", "referral code",
            "promo code", "discount code", "special discount", "coupon code",
            "use coupon", "lifetime deal", "pricing plan", "buy now",
            "purchase today", "save 20%", "save 30%", "save 50%"
        ]
        matched_strong = [m for m in strong_markers if m in text]
        if matched_strong:
            return True, matched_strong

        # Multi-category markers
        cta_markers = [
            "check out our", "visit our website", "visit our site", "try our",
            "click here to", "learn more at", "download our", "book a demo",
            "request a demo", "get started with our"
        ]
        signup_markers = [
            "sign up", "sign-up", "register now", "create an account",
            "join our waitlist", "join the waitlist", "subscribe to our newsletter",
            "subscribe now"
        ]
        promo_terms = [
            "limited time offer", "special offer", "exclusive deal", "exclusive offer",
            "free trial", "money-back guarantee", "best price", "discount"
        ]

        matched_cta = [m for m in cta_markers if m in text]
        matched_signup = [m for m in signup_markers if m in text]
        matched_promo = [m for m in promo_terms if m in text]

        active_categories = 0
        all_matched = []
        if matched_cta:
            active_categories += 1
            all_matched.extend(matched_cta)
        if matched_signup:
            active_categories += 1
            all_matched.extend(matched_signup)
        if matched_promo:
            active_categories += 1
            all_matched.extend(matched_promo)

        # Block if at least 2 distinct marker categories are present
        if active_categories >= 2:
            return True, all_matched

        return False, []

    @staticmethod
    def _parse_link_limit(policy: str) -> Optional[int]:
        """Parse link policy string: 'none' -> 0, 'allowed' -> None, 'restricted' -> 2, 'max_N'/'max:N' -> N."""
        if not policy or policy == "none":
            return 0
        if policy == "allowed":
            return None
        if policy == "restricted":
            return 2
        match = re.search(r'max[:_ ]?(\d+)', policy, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return 2

    async def check_rules(
        self,
        rendition: RenditionSchema,
        destination: Any,
        db: Optional[AsyncSession] = None,
        is_automated_request: bool = True
    ) -> List[str]:
        """
        Validate all posting rules against the rendition and destination.
        Fail-closed: Refuses destination if any required rule is missing.
        Raises ConnectorException for blocking violations, or returns warnings list.
        """
        dest_name = getattr(destination, "name", "Unknown Destination")
        connector_key = getattr(destination, "connector_key", "")

        # Extract rules from DestinationModel or DestinationSchema
        rules_dict = getattr(destination, "rules", None) or {}

        # 1. Fail-closed Check for Missing Rules
        def get_rule(attr: str):
            val = getattr(destination, attr, None)
            if val is not None:
                return val
            if isinstance(rules_dict, dict) and attr in rules_dict:
                return rules_dict[attr]
            return None

        enabled = get_rule("enabled") if get_rule("enabled") is not None else True
        automation_allowed = get_rule("automation_allowed")
        frequency_cap = get_rule("frequency_cap")
        frequency_period_hours = get_rule("frequency_period_hours") or 24
        self_promo_allowed = get_rule("self_promo_allowed")
        link_policy = get_rule("link_policy")
        disclosure_required = get_rule("disclosure_required")

        # 1. Destination Enabled Check
        if enabled is False:
            raise ConnectorException(
                code=ErrorCode.CONNECTOR_DISABLED,
                message=f"Destination '{dest_name}' is currently disabled in the catalogue.",
                retryable=False,
                status_code=400
            )

        # 2. Automation Allowance Check
        if is_automated_request and automation_allowed is False:
            raise ConnectorException(
                code=ErrorCode.CONNECTOR_DISABLED,
                message=(
                    f"Destination '{dest_name}' prohibits automated posting. "
                    "Use assisted publishing workflow instead."
                ),
                retryable=False,
                status_code=400
            )

        # 3. Fail-closed Check for Missing Rules
        required_rules = {
            "automation_allowed": automation_allowed,
            "frequency_cap": frequency_cap,
            "self_promo_allowed": self_promo_allowed,
            "link_policy": link_policy,
            "disclosure_required": disclosure_required
        }
        missing_rules = [r for r, v in required_rules.items() if v is None]
        if missing_rules:
            raise ConnectorException(
                code=ErrorCode.DEST_SPEC_VIOLATION,
                message=(
                    f"Destination '{dest_name}' has missing or incomplete posting rules "
                    f"({', '.join(missing_rules)}). Refusing publish (fail-closed)."
                ),
                retryable=False,
                details={"missing_rules": missing_rules},
                status_code=422
            )

        # 4. Frequency Cap Check
        if db is not None and frequency_cap and frequency_cap > 0:
            dest_id = getattr(destination, "id", None)
            if dest_id:
                since = datetime.now(timezone.utc) - timedelta(hours=frequency_period_hours)
                stmt = select(func.count(PublicationRecordModel.id)).where(
                    PublicationRecordModel.destination_id == dest_id,
                    PublicationRecordModel.created_at >= since,
                    PublicationRecordModel.status.in_(["published", "queued", "running"])
                )
                res = await db.execute(stmt)
                recent_count = res.scalar() or 0
                if recent_count >= frequency_cap:
                    raise ConnectorException(
                        code=ErrorCode.DEST_RULE_FREQUENCY_CAP,
                        message=(
                            f"Frequency cap exceeded for destination '{dest_name}': "
                            f"{recent_count}/{frequency_cap} posts published in the last {frequency_period_hours} hours. "
                            "Second post inside the cap is blocked to protect community standing."
                        ),
                        retryable=True,
                        details={
                            "recent_count": recent_count,
                            "cap": frequency_cap,
                            "period_hours": frequency_period_hours,
                            "retry_after_seconds": int(3600 * frequency_period_hours)
                        },
                        status_code=429
                    )

        # 5. Self-Promotion Policy
        if not self_promo_allowed:
            is_promo, markers = self._is_self_promotional(rendition)
            if is_promo:
                raise ConnectorException(
                    code=ErrorCode.DEST_SPEC_VIOLATION,
                    message=(
                        f"Destination '{dest_name}' prohibits self-promotional content. "
                        f"Detected promotional markers: {', '.join(markers)}."
                    ),
                    retryable=False,
                    details={"matched_markers": markers},
                    status_code=422
                )

        # 6. Link Policy
        links = self._extract_links(f"{rendition.body} {rendition.summary or ''}")
        max_links = self._parse_link_limit(link_policy)
        if max_links is not None and len(links) > max_links:
            if max_links == 0:
                msg = f"Destination '{dest_name}' strictly prohibits external links (found {len(links)} link(s))."
            else:
                msg = f"Destination '{dest_name}' allows at most {max_links} external links (found {len(links)} link(s))."
            raise ConnectorException(
                code=ErrorCode.DEST_SPEC_VIOLATION,
                message=msg,
                retryable=False,
                details={"links_found": links, "max_allowed": max_links},
                status_code=422
            )

        # 7. AI-Content Disclosure Policy
        if disclosure_required and rendition.is_ai_generated:
            if not rendition.ai_disclosure_text or len(rendition.ai_disclosure_text.strip()) == 0:
                raise ConnectorException(
                    code=ErrorCode.DEST_SPEC_VIOLATION,
                    message=(
                        f"Destination '{dest_name}' requires explicit AI-content disclosure statement "
                        "for AI-generated renditions."
                    ),
                    retryable=False,
                    status_code=422
                )

        # 8. Connector Manifest Limits Validation
        if connector_key:
            try:
                manifest = registry.get_manifest(connector_key)
                fl = manifest.format_limits

                # Title limits
                title_len = len(rendition.title.strip()) if rendition.title else 0
                if title_len < fl.title_min_chars:
                    raise ConnectorException(
                        code=ErrorCode.DEST_SPEC_VIOLATION,
                        message=f"Title is too short for {connector_key} (min {fl.title_min_chars} chars)",
                        retryable=False,
                        status_code=422
                    )
                if title_len > fl.title_max_chars:
                    raise ConnectorException(
                        code=ErrorCode.DEST_SPEC_VIOLATION,
                        message=f"Title exceeds {connector_key} limit (max {fl.title_max_chars} chars)",
                        retryable=False,
                        status_code=422
                    )

                # Body limits
                body_len = len(rendition.body.strip()) if rendition.body else 0
                if body_len < fl.body_min_chars:
                    raise ConnectorException(
                        code=ErrorCode.DEST_SPEC_VIOLATION,
                        message=f"Body is too short for {connector_key} (min {fl.body_min_chars} chars)",
                        retryable=False,
                        status_code=422
                    )
                if body_len > fl.body_max_chars:
                    raise ConnectorException(
                        code=ErrorCode.DEST_SPEC_VIOLATION,
                        message=f"Body exceeds {connector_key} limit (max {fl.body_max_chars} chars)",
                        retryable=False,
                        status_code=422
                    )

                # Tag limits
                if len(rendition.tags) > fl.max_tags:
                    raise ConnectorException(
                        code=ErrorCode.DEST_SPEC_VIOLATION,
                        message=f"Too many tags for {connector_key} (max {fl.max_tags})",
                        retryable=False,
                        status_code=422
                    )
            except Exception as e:
                if isinstance(e, ConnectorException):
                    raise e

        return []


rules_engine = PostingRulesEngine()
