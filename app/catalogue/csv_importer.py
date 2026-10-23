"""CSV Destination importer with URL normalisation, duplicate detection, and reachability checks."""

import csv
import io
import uuid
from urllib.parse import urlparse, urlunparse
from typing import List, Tuple, Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.destination import DestinationModel
from app.schemas.destination import CSVImportSummary, CSVImportRowResult
from app.config import settings


def normalise_url(raw_url: str) -> str:
    """Normalise URL by lowercasing scheme/host, removing default ports and trailing slashes."""
    if not raw_url:
        return ""
    raw = raw_url.strip()
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = "https://" + raw

    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Remove standard ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    # Remove www prefix for consistent matching
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parsed.path.rstrip("/")
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


async def check_reachability(url: str, check_enabled: bool = True) -> Tuple[bool, str]:
    """Test URL reachability with a short safe timeout (3.0s)."""
    if not check_enabled:
        return True, "Check skipped"

    async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
        try:
            resp = await client.head(url)
            if resp.status_code < 500:
                return True, f"HTTP {resp.status_code}"
            # Retry with GET in case HEAD is disallowed by host
            resp_get = await client.get(url)
            if resp_get.status_code < 500:
                return True, f"HTTP {resp_get.status_code}"
            return False, f"Server returned HTTP {resp_get.status_code}"
        except httpx.RequestError as exc:
            # If in simulation mode and URL is a local mock or synthetic test domain, accept
            if settings.SIMULATION_MODE and ("localhost" in url or ".test" in url or "example.com" in url):
                return True, "Simulated reachability success"
            return False, f"Network error: {str(exc)}"


async def import_destinations_from_csv(
    csv_content: str,
    db: AsyncSession,
    perform_reachability: bool = True
) -> CSVImportSummary:
    """Process a CSV file containing destinations and import valid, non-duplicate entries."""
    reader = csv.DictReader(io.StringIO(csv_content))
    summary = CSVImportSummary(total_rows=0, imported_count=0, skipped_duplicates=0, errors_count=0)

    # Load existing (normalised_url, platform_key) sets to prevent DB duplicates
    stmt = select(DestinationModel.normalised_url, DestinationModel.platform_key)
    res = await db.execute(stmt)
    existing_set = {(row[0], row[1]) for row in res.fetchall()}

    row_index = 1
    for row in reader:
        row_index += 1
        summary.total_rows += 1

        name = row.get("name", "").strip()
        raw_url = row.get("url", "").strip()
        platform_key = row.get("platform_key", "").strip()
        connector_key = row.get("connector_key", "").strip() or platform_key

        if not name or not raw_url or not platform_key:
            summary.errors_count += 1
            summary.rows.append(CSVImportRowResult(
                row_number=row_index,
                name=name or "Unknown",
                url=raw_url,
                status="error",
                reason="Missing required columns (name, url, platform_key)"
            ))
            continue

        norm_url = normalise_url(raw_url)

        # Duplicate check
        if (norm_url, platform_key) in existing_set:
            summary.skipped_duplicates += 1
            summary.rows.append(CSVImportRowResult(
                row_number=row_index,
                name=name,
                url=raw_url,
                status="skipped_duplicate",
                reason=f"Destination with URL '{norm_url}' on platform '{platform_key}' already exists"
            ))
            continue

        # Reachability check
        if perform_reachability:
            reachable, reason = await check_reachability(raw_url)
            if not reachable:
                summary.errors_count += 1
                summary.rows.append(CSVImportRowResult(
                    row_number=row_index,
                    name=name,
                    url=raw_url,
                    status="error",
                    reason=f"Destination unreachable: {reason}"
                ))
                continue

        # Parse tags
        tags_raw = row.get("audience_tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        # Parse boolean helpers
        def to_bool(val, default=True):
            if val is None or val == "":
                return default
            return str(val).lower() in ("true", "1", "yes", "t")

        try:
            dest_id = f"dest_{uuid.uuid4().hex[:12]}"
            dest_obj = DestinationModel(
                id=dest_id,
                name=name,
                url=raw_url,
                normalised_url=norm_url,
                platform_key=platform_key,
                connector_key=connector_key,
                surface=row.get("surface", "main").strip() or "main",
                category=row.get("category", "general").strip() or "general",
                audience_tags=tags,
                language=row.get("language", "en").strip() or "en",
                geo=row.get("geo", "global").strip() or "global",
                est_audience=int(row.get("est_audience", 0) or 0),
                rules_url=row.get("rules_url", "").strip() or None,
                frequency_cap=int(row.get("frequency_cap", 10) or 10),
                self_promo_allowed=to_bool(row.get("self_promo_allowed"), True),
                link_policy=row.get("link_policy", "allowed").strip() or "allowed",
                disclosure_required=to_bool(row.get("disclosure_required"), False),
                automation_allowed=to_bool(row.get("automation_allowed"), True),
                relevance_score=float(row.get("relevance_score", 3.0) or 3.0),
                relevance_reason=row.get("relevance_reason", "").strip() or None,
                level=row.get("level", "standard").strip() or "standard",
                enabled=to_bool(row.get("enabled"), True)
            )

            db.add(dest_obj)
            existing_set.add((norm_url, platform_key))
            summary.imported_count += 1
            summary.rows.append(CSVImportRowResult(
                row_number=row_index,
                name=name,
                url=raw_url,
                status="imported"
            ))
        except Exception as e:
            summary.errors_count += 1
            summary.rows.append(CSVImportRowResult(
                row_number=row_index,
                name=name,
                url=raw_url,
                status="error",
                reason=f"Database insertion failed: {str(e)}"
            ))

    await db.commit()
    return summary
