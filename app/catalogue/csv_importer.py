"""CSV Destination importer with URL normalisation, duplicate detection, reachability, SSRF guard, and enrichment."""

import csv
import io
import re
import socket
import ipaddress
import asyncio
import uuid
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from typing import List, Tuple, Optional, Dict, Any, Set
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.destination import DestinationModel
from app.schemas.destination import CSVImportSummary, CSVImportRowResult
from app.config import settings

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "ref_src", "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid"
}


def strip_tracking_params(query: str) -> str:
    """Strip analytics, affiliate, and social tracking query parameters."""
    if not query:
        return ""
    params = parse_qsl(query, keep_blank_values=True)
    filtered = [(k, v) for k, v in params if k.lower() not in TRACKING_PARAMS]
    return urlencode(filtered)


def normalise_url(raw_url: str) -> str:
    """
    Normalise URL:
    - lowercase scheme and hostname
    - strip www prefix
    - strip default ports (:80, :443)
    - strip trailing slashes
    - strip tracking parameters (utm_*, ref, etc.)
    """
    if not raw_url:
        return ""
    raw = raw_url.strip()
    raw_lower = raw.lower()
    if not raw_lower.startswith("http://") and not raw_lower.startswith("https://"):
        raw = "https://" + raw

    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Strip default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    # Strip www prefix
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parsed.path.rstrip("/")
    clean_query = strip_tracking_params(parsed.query)

    return urlunparse((scheme, netloc, path, "", clean_query, ""))


def is_ssrf_risk(host: str, allow_local: bool = False) -> bool:
    """
    SSRF Guard:
    Checks if hostname or IP resolves to private, loopback, or link-local addresses.
    Refuses them unless allow_local is explicitly True.
    """
    if allow_local:
        return False

    clean_host = host.split(":")[0].strip()

    # Check direct IP
    try:
        ip = ipaddress.ip_address(clean_host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        pass

    # Check DNS resolution
    try:
        addrinfos = socket.getaddrinfo(clean_host, None)
        for ai in addrinfos:
            ip = ipaddress.ip_address(ai[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return True
    except Exception:
        return False

    return False


async def check_reachability(
    url: str,
    check_enabled: bool = True,
    allow_local: bool = False,
    client: Optional[httpx.AsyncClient] = None
) -> Tuple[bool, str, str, Dict[str, Any]]:
    """
    Check URL reachability with SSRF guard, timeout, redirect tracking, and enrichment hints.
    Returns: (reachable: bool, reason: str, final_url: str, enrichment: dict)
    """
    if not check_enabled:
        return True, "Check skipped", url, {}

    parsed = urlparse(url)
    if is_ssrf_risk(parsed.netloc, allow_local=allow_local):
        return False, "SSRF guard: private or link-local address disallowed", url, {}

    enrichment: Dict[str, Any] = {}
    timeout = 3.0

    async def _inspect(c: httpx.AsyncClient):
        # 1. Fetch destination with redirects
        resp = await c.get(url, timeout=timeout, follow_redirects=True)
        final_url = str(resp.url)

        if resp.status_code >= 400:
            return False, f"Server returned HTTP {resp.status_code}", final_url, enrichment

        # Platform detection & enrichment hints
        headers_str = " ".join(f"{k}:{v}" for k, v in resp.headers.items()).lower()
        body_sample = resp.text[:4000].lower() if hasattr(resp, "text") else ""

        if "discourse" in headers_str or "discourse" in body_sample:
            enrichment["platform_detected"] = "discourse"
        elif "lemmy" in headers_str or "lemmy" in body_sample:
            enrichment["platform_detected"] = "lemmy"
        elif "ghost" in headers_str or "ghost" in body_sample:
            enrichment["platform_detected"] = "ghost"
        elif "dev.to" in url or "forem" in body_sample:
            enrichment["platform_detected"] = "devto"

        # Check for rules link hint
        rules_match = re.search(r'href=["\'](/rules|/guidelines|/about/rules)["\']', body_sample)
        if rules_match:
            base_origin = f"{parsed.scheme}://{parsed.netloc}"
            enrichment["rules_url"] = base_origin + rules_match.group(1)

        # 2. Robots.txt courtesy check
        try:
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            robots_resp = await c.get(robots_url, timeout=2.0)
            if robots_resp.status_code == 200:
                enrichment["robots_txt_present"] = True
                if "disallow: /" in robots_resp.text.lower():
                    enrichment["robots_disallow_root"] = True
        except Exception:
            pass

        return True, f"HTTP {resp.status_code}", final_url, enrichment

    try:
        if client:
            return await _inspect(client)
        else:
            async with httpx.AsyncClient(timeout=timeout) as c:
                return await _inspect(c)
    except httpx.RequestError as exc:
        if settings.SIMULATION_MODE and ("localhost" in url or ".test" in url or "example.com" in url):
            return True, "Simulated reachability success", url, {}
        return False, f"Network error: {str(exc)}", url, {}


async def import_destinations_from_csv(
    csv_content: str,
    db: AsyncSession,
    perform_reachability: bool = True,
    allow_local: bool = False,
    concurrency_limit: int = 50,
    http_client: Optional[httpx.AsyncClient] = None
) -> CSVImportSummary:
    """
    Process a CSV file containing destinations and import valid, non-duplicate entries.
    Features:
    - Normalisation (lowercase, strip www, trailing slash, default port, tracking parameters)
    - Deduplication by normalised URL + platform (including redirected destination URLs)
    - Reachability check with SSRF guard and robots.txt inspection
    - Metadata and platform enrichment
    - High-throughput asynchronous batching
    """
    if isinstance(csv_content, bytes):
        csv_text = csv_content.decode("utf-8", errors="replace")
    else:
        csv_text = str(csv_content)
    reader = list(csv.DictReader(io.StringIO(csv_text)))
    summary = CSVImportSummary(total_rows=0, imported_count=0, skipped_duplicates=0, errors_count=0)

    # Load existing (normalised_url, platform_key) sets to prevent DB duplicates
    stmt = select(DestinationModel.normalised_url, DestinationModel.platform_key)
    res = await db.execute(stmt)
    existing_set: Set[Tuple[str, str]] = {(row[0], row[1]) for row in res.fetchall()}

    semaphore = asyncio.Semaphore(concurrency_limit)

    async def process_row(row_index: int, row: Dict[str, str], client: Optional[httpx.AsyncClient]) -> Optional[Dict[str, Any]]:
        name = row.get("name", "").strip()
        raw_url = row.get("url", "").strip()
        platform_key = row.get("platform_key", "").strip()
        connector_key = row.get("connector_key", "").strip() or platform_key

        if not name or not raw_url or not platform_key:
            return {
                "status": "error",
                "row_result": CSVImportRowResult(
                    row_number=row_index,
                    name=name or "Unknown",
                    url=raw_url,
                    status="invalid",
                    reason="Missing required columns (name, url, platform_key)"
                )
            }

        norm_url = normalise_url(raw_url)

        # Initial duplicate check
        if (norm_url, platform_key) in existing_set:
            return {
                "status": "duplicate",
                "row_result": CSVImportRowResult(
                    row_number=row_index,
                    name=name,
                    url=raw_url,
                    status="duplicate",
                    reason=f"Destination with URL '{norm_url}' on platform '{platform_key}' already exists"
                )
            }

        # Reachability & SSRF check
        enrichment: Dict[str, Any] = {}
        target_norm_url = norm_url

        if perform_reachability:
            async with semaphore:
                reachable, reason, final_url, enrichment = await check_reachability(
                    raw_url,
                    check_enabled=True,
                    allow_local=allow_local,
                    client=client
                )

            if not reachable:
                return {
                    "status": "unreachable",
                    "row_result": CSVImportRowResult(
                        row_number=row_index,
                        name=name,
                        url=raw_url,
                        status="unreachable",
                        reason=reason
                    )
                }

            # Check if redirect created a duplicate
            if final_url and final_url != raw_url:
                target_norm_url = normalise_url(final_url)
                if (target_norm_url, platform_key) in existing_set:
                    return {
                        "status": "duplicate",
                        "row_result": CSVImportRowResult(
                            row_number=row_index,
                            name=name,
                            url=raw_url,
                            status="duplicate",
                            reason=f"Redirected URL '{target_norm_url}' on platform '{platform_key}' already exists"
                        )
                    }

        # Determine effective platform key if enrichment detected it
        effective_platform = platform_key
        if platform_key in ("auto", "detect") and enrichment.get("platform_detected"):
            effective_platform = enrichment["platform_detected"]
            connector_key = effective_platform

        # Parse tags
        tags_raw = row.get("audience_tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        def to_bool(val, default=True):
            if val is None or val == "":
                return default
            return str(val).lower() in ("true", "1", "yes", "t")

        rules_url = row.get("rules_url", "").strip() or enrichment.get("rules_url")

        dest_id = f"dest_{uuid.uuid4().hex[:12]}"
        dest_obj = DestinationModel(
            id=dest_id,
            name=name,
            url=raw_url,
            normalised_url=target_norm_url,
            platform_key=effective_platform,
            connector_key=connector_key,
            surface=row.get("surface", "main").strip() or "main",
            category=row.get("category", "general").strip() or "general",
            audience_tags=tags,
            language=row.get("language", "en").strip() or "en",
            geo=row.get("geo", "global").strip() or "global",
            est_audience=int(row.get("est_audience", 0) or 0),
            rules_url=rules_url,
            frequency_cap=int(row.get("frequency_cap", 10) or 10),
            frequency_period_hours=int(row.get("frequency_period_hours", 24) or 24),
            self_promo_allowed=to_bool(row.get("self_promo_allowed"), True),
            link_policy=row.get("link_policy", "allowed").strip() or "allowed",
            disclosure_required=to_bool(row.get("disclosure_required"), False),
            automation_allowed=to_bool(row.get("automation_allowed"), True),
            relevance_score=float(row.get("relevance_score", 3.0) or 3.0),
            relevance_reason=row.get("relevance_reason", "").strip() or None,
            level=row.get("level", "standard").strip() or "standard",
            enabled=to_bool(row.get("enabled"), True),
            catalogue_only=to_bool(row.get("catalogue_only"), False)
        )

        return {
            "status": "accepted",
            "model": dest_obj,
            "dedup_key": (target_norm_url, effective_platform),
            "row_result": CSVImportRowResult(
                row_number=row_index,
                name=name,
                url=raw_url,
                status="accepted"
            )
        }

    # Execute rows concurrently
    if http_client:
        tasks = [
            process_row(idx + 2, r, http_client if perform_reachability else None)
            for idx, r in enumerate(reader)
        ]
        results = await asyncio.gather(*tasks)
    else:
        async with httpx.AsyncClient(timeout=3.0) as client:
            tasks = [
                process_row(idx + 2, r, client if perform_reachability else None)
                for idx, r in enumerate(reader)
            ]
            results = await asyncio.gather(*tasks)

    for res_item in results:
        summary.total_rows += 1
        st = res_item["status"]
        if st == "accepted":
            if res_item["dedup_key"] in existing_set:
                summary.skipped_duplicates += 1
                summary.rows.append(CSVImportRowResult(
                    row_number=res_item["row_result"].row_number,
                    name=res_item["row_result"].name,
                    url=res_item["row_result"].url,
                    status="duplicate",
                    reason=f"Duplicate within batch: URL '{res_item['dedup_key'][0]}' on platform '{res_item['dedup_key'][1]}' already processed"
                ))
            else:
                summary.imported_count += 1
                existing_set.add(res_item["dedup_key"])
                db.add(res_item["model"])
                summary.rows.append(res_item["row_result"])
        elif st == "duplicate":
            summary.skipped_duplicates += 1
            summary.rows.append(res_item["row_result"])
        elif st in ("error", "unreachable"):
            summary.errors_count += 1
            summary.rows.append(res_item["row_result"])

    await db.commit()
    return summary
