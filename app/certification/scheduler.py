"""Recertification Scheduler enforcing 30-day certification lifetime and demotion alerts."""

import uuid
import hmac
import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.models.destination import DestinationModel
from app.models.alert import AlertModel
from app.certification.harness import CertificationHarness, CertificationReport
from app.config import settings

logger = logging.getLogger("incubrix.recertification")


class RecertificationScheduler:
    """Enforces continuous platform health and recertification within 30-day hard limit."""

    @classmethod
    async def find_destinations_needing_recertification(
        cls,
        db: AsyncSession,
        as_of: Optional[datetime] = None,
        max_age_days: int = 30
    ) -> List[DestinationModel]:
        """
        Query destinations needing recertification.
        Supports a fake clock via the `as_of` parameter for deterministic testing.
        Excludes demoted and catalogue_only destinations.
        """
        current_time = as_of or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        cutoff = current_time - timedelta(days=max_age_days)

        stmt = select(DestinationModel).where(
            DestinationModel.status != "demoted",
            DestinationModel.catalogue_only == False,  # noqa: E712
            or_(
                DestinationModel.last_certified_at.is_(None),
                DestinationModel.last_certified_at <= cutoff
            )
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def recertify_destination(
        cls,
        destination: DestinationModel,
        db: AsyncSession,
        environment: str = "mock",
        webhook_url: Optional[str] = None,
        webhook_secret: Optional[str] = None
    ) -> CertificationReport:
        """
        Run recertification on a single destination.
        If failing, demote destination, disable it, and create a system alert.
        """
        report = await CertificationHarness.run_certification(
            destination=destination,
            environment=environment
        )

        if not report.passed:
            # 1. Demote and disable destination
            destination.status = "demoted"
            destination.enabled = False

            # 2. Log persistent alert to DB
            alert_id = f"alert_{uuid.uuid4().hex[:12]}"
            alert = AlertModel(
                id=alert_id,
                destination_id=destination.id,
                destination_name=destination.name,
                alert_type="recertification_failed",
                severity="high",
                message=(
                    f"Recertification failed for '{destination.name}' ({destination.connector_key}): "
                    f"{report.error_message or report.verdict}. Destination demoted and excluded from distribution."
                ),
                created_at=datetime.now(timezone.utc)
            )
            db.add(alert)
            await db.commit()
            await db.refresh(destination)

            logger.error(
                f"Recertification failure on {destination.id} ({destination.name}). "
                f"Demoted destination and generated alert {alert_id}."
            )

            # 3. Optional signed webhook notification
            target_webhook = webhook_url or getattr(settings, "ALERT_WEBHOOK_URL", None)
            secret = webhook_secret or getattr(settings, "WEBHOOK_SIGNING_SECRET", "incubrix_alert_secret")
            if target_webhook:
                await cls._send_signed_alert(target_webhook, secret, alert)

        return report

    @classmethod
    async def _send_signed_alert(cls, url: str, secret: str, alert: AlertModel):
        """Send an alert payload to a remote webhook signed with HMAC-SHA256."""
        payload = {
            "event": "destination.recertification_failed",
            "alert_id": alert.id,
            "destination_id": alert.destination_id,
            "destination_name": alert.destination_name,
            "severity": alert.severity,
            "message": alert.message,
            "created_at": alert.created_at.isoformat() if alert.created_at else datetime.now(timezone.utc).isoformat()
        }
        body_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    url,
                    content=body_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-IncuBrix-Signature": signature
                    }
                )
        except Exception as exc:
            logger.warning(f"Failed to deliver recertification alert webhook to {url}: {exc}")

    @classmethod
    async def run_batch(
        cls,
        db: AsyncSession,
        as_of: Optional[datetime] = None,
        max_age_days: int = 30,
        environment: str = "mock"
    ) -> List[Dict[str, Any]]:
        """Run recertification across all destinations needing it."""
        destinations = await cls.find_destinations_needing_recertification(
            db, as_of=as_of, max_age_days=max_age_days
        )
        summaries = []
        for dest in destinations:
            report = await cls.recertify_destination(dest, db, environment=environment)
            summaries.append({
                "destination_id": dest.id,
                "name": dest.name,
                "passed": report.passed,
                "verdict": report.verdict,
                "status": dest.status
            })
        return summaries
