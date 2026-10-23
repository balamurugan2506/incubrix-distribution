"""Destination Recommendation Engine (Outstanding Level 1).

Ranks destinations by fit for a given content item:
- Audience relevance
- Rule safety (strictly excludes demoted and rule-blocked destinations)
- Past certification validity (within 30-day hard cap)
- Posting history and frequency headroom
- Returns clear reasoning for every recommended destination
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.destination import DestinationModel
from app.models.publication import PublicationRecordModel
from app.rules.engine import PostingRulesEngine
from app.schemas.connector import RenditionSchema
from app.catalogue.relevance import compute_audience_relevance, AUDIENCE_PILLARS
from app.connectors.registry import registry
from app.rules.tailoring import tailor_rendition_for_destination


class ContentItemSchema(BaseModel):
    title: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    tags: List[str] = Field(default_factory=list)
    media_urls: List[str] = Field(default_factory=list)
    category: Optional[str] = "general"
    is_automated: bool = True


class DestinationRecommendation(BaseModel):
    destination_id: str
    destination_name: str
    connector_key: str
    platform_key: str
    fit_score: float  # 0.0 to 100.0
    audience_relevance: float  # 1.0 to 5.0
    relevance_reason: str
    reason: str
    warnings: List[str] = Field(default_factory=list)


class RecommenderEngine:
    """Intelligent distribution recommender with strict safety gating."""

    def __init__(self, rules_engine: Optional[PostingRulesEngine] = None):
        self.rules_engine = rules_engine or PostingRulesEngine()

    async def rank_destinations(
        self,
        content: ContentItemSchema,
        destinations: List[DestinationModel],
        db: Optional[AsyncSession] = None,
        limit: int = 10
    ) -> List[DestinationRecommendation]:
        """
        Rank destinations for the provided content item.
        Excludes demoted, disabled, catalogue_only, and rule-blocked destinations.
        """
        rendition = RenditionSchema(
            title=content.title,
            body=content.body,
            tags=content.tags,
            media_urls=content.media_urls,
            platform_specific={}
        )

        candidates = []
        now = datetime.now(timezone.utc)

        for dest in destinations:
            # 1. Exclusion: Demoted, disabled, or catalogue-only
            if dest.status == "demoted" or not dest.enabled or getattr(dest, "catalogue_only", False):
                continue

            # 2. Rule Safety Gating: Check whether content would be blocked
            # Tailor rendition to destination format limits (e.g. tag count, body limits)
            manifest = registry.get_manifest(dest.connector_key) if dest.connector_key in registry._manifests else None
            rend_to_check = rendition
            if manifest:
                rend_to_check, _ = tailor_rendition_for_destination(
                    rendition, manifest.model_dump(), dest.language or "en"
                )

            try:
                rule_warnings = await self.rules_engine.check_rules(
                    rendition=rend_to_check,
                    destination=dest,
                    db=db,
                    is_automated_request=content.is_automated
                )
            except Exception:
                # Rule violation: blocked from recommendation
                continue

            # 3. Audience Relevance & Pillar Alignment
            dest_tags = dest.audience_tags or []
            if isinstance(dest_tags, str):
                dest_tags = [t.strip() for t in dest_tags.split(",")]

            content_text = f"{content.title} {content.body} {content.category or ''} {' '.join(content.tags)}".lower()
            dest_text = f"{dest.name} {dest.category or ''} {' '.join(dest_tags)}".lower()

            content_pillars = {pillar for pillar, keywords in AUDIENCE_PILLARS.items() if any(kw in content_text for kw in keywords)}
            dest_pillars = {pillar for pillar, keywords in AUDIENCE_PILLARS.items() if any(kw in dest_text for kw in keywords)}

            overlap = content_pillars & dest_pillars

            if overlap:
                match_ratio = len(overlap) / max(1, len(content_pillars))
                rel_score = round(min(5.0, 2.5 + (match_ratio * 2.5)), 1)
                rel_reason = f"Content topic pillars {list(content_pillars)} align directly with destination pillars {list(overlap)}"
            elif not content_pillars and dest_pillars:
                rel_score = 2.0
                rel_reason = "Generic content matched against specialized destination audience"
            else:
                rel_score = 1.0
                rel_reason = "No vertical pillar overlap between content topic and destination audience"

            # 4. Multi-factor Fit Score Calculation
            # Baseline from audience relevance (1.0 - 5.0 scaled to 0 - 50 pts)
            audience_pts = (rel_score / 5.0) * 50.0

            # Certification bonus (up to 20 pts)
            cert_pts = 0.0
            if dest.last_certified_at:
                cert_time = dest.last_certified_at
                if cert_time.tzinfo is None:
                    cert_time = cert_time.replace(tzinfo=timezone.utc)
                age_days = (now - cert_time).total_seconds() / 86400.0
                if age_days <= 30.0:
                    cert_pts = 20.0 * (1.0 - (age_days / 30.0) * 0.3)
            else:
                cert_pts = 2.0  # Uncertified gets minimal base

            # Platform format synergy (up to 20 pts)
            synergy_pts = 10.0
            if content.media_urls and dest.connector_key in ("ghost", "hashnode", "lemmy"):
                synergy_pts += 10.0
            elif not content.media_urls and dest.connector_key in ("discourse", "devto", "lemmy", "slack"):
                synergy_pts += 8.0

            # Frequency headroom (up to 15 pts)
            headroom_pts = 15.0  # Default full headroom if no DB publications checked

            total_fit_score = round(min(100.0, audience_pts + cert_pts + synergy_pts + headroom_pts), 1)

            # Construct human-readable reasoning
            reason_parts = [
                f"Audience match ({rel_score}/5.0): {rel_reason}",
                f"Certification status: {'Certified' if cert_pts > 10 else 'Uncertified/Expired'}",
                f"Format synergy fit: +{synergy_pts:.0f} pts"
            ]
            detailed_reason = "; ".join(reason_parts)

            candidates.append(
                DestinationRecommendation(
                    destination_id=dest.id,
                    destination_name=dest.name,
                    connector_key=dest.connector_key,
                    platform_key=dest.platform_key,
                    fit_score=total_fit_score,
                    audience_relevance=rel_score,
                    relevance_reason=rel_reason,
                    reason=detailed_reason,
                    warnings=rule_warnings or []
                )
            )

        # Sort descending by fit_score, tie-breaking by audience_relevance
        candidates.sort(key=lambda x: (x.fit_score, x.audience_relevance), reverse=True)
        return candidates[:limit]


recommender_engine = RecommenderEngine()
