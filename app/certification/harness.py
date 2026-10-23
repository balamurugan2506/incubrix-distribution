"""Publication Certification Harness verifying end-to-end publish, visibility, and deletion."""

import uuid
import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.models.destination import DestinationModel
from app.models.certification import CertificationRecordModel
from app.schemas.connector import (
    RenditionSchema,
    DestinationSchema,
    ConnectionSchema,
    PublishResult,
    StatusResult,
    DeleteResult,
    AssistPackResult
)
from app.connectors.registry import registry
from app.storage.evidence import evidence_storage
from app.database import AsyncSessionLocal
from app.logging_conf import logger
from app.rules.errors import ConnectorException, ErrorCode


class CertificationStepReceipt(BaseModel):
    step: str
    status: str  # passed, failed, skipped
    timestamp: str
    details: Dict[str, Any] = Field(default_factory=dict)


class CertificationReport(BaseModel):
    certification_id: str
    destination_id: str
    destination_name: str
    connector_key: str
    connector_version: str
    environment: str  # "real local instance" or "mock"
    verdict: str = "inconclusive"  # passed, failed (demote), inconclusive (needs attention)
    passed: bool = False
    platform_post_id: Optional[str] = None
    live_url: Optional[str] = None
    deletion_confirmed: bool = False
    evidence_file: Optional[str] = None
    started_at: str
    completed_at: str = ""
    steps: List[CertificationStepReceipt] = Field(default_factory=list)
    error_message: Optional[str] = None


class CertificationHarness:
    """Executes the complete publication certification contract with guaranteed cleanup and demotion on schema failure."""

    @classmethod
    async def run_certification(
        cls,
        destination: DestinationModel,
        connection: Optional[ConnectionSchema] = None,
        environment: str = "mock"
    ) -> CertificationReport:
        # Standardize environment label per brief (never call a mock real)
        env_label = "real local instance" if "real" in environment.lower() or "local" in environment.lower() else "mock"
        cert_id = f"cert_{uuid.uuid4().hex[:12]}"
        started_at = datetime.now(timezone.utc).isoformat()
        manifest = registry.get_manifest(destination.connector_key)
        connector = registry.get_connector(destination.connector_key)

        steps: List[CertificationStepReceipt] = []

        report = CertificationReport(
            certification_id=cert_id,
            destination_id=destination.id,
            destination_name=destination.name,
            connector_key=destination.connector_key,
            connector_version=manifest.version,
            environment=env_label,
            verdict="inconclusive",
            passed=False,
            started_at=started_at,
            completed_at=""
        )

        dest_schema = DestinationSchema(
            id=destination.id,
            name=destination.name,
            url=destination.url,
            platform_key=destination.platform_key,
            connector_key=destination.connector_key,
            surface=destination.surface,
            instance_config=destination.instance_config or {},
            rules={
                "frequency_cap": destination.frequency_cap or 10,
                "frequency_period_hours": getattr(destination, "frequency_period_hours", 24) or 24,
                "self_promo_allowed": destination.self_promo_allowed if destination.self_promo_allowed is not None else True,
                "link_policy": destination.link_policy or "allowed",
                "disclosure_required": destination.disclosure_required if destination.disclosure_required is not None else False,
                "automation_allowed": destination.automation_allowed if destination.automation_allowed is not None else True
            }
        )

        conn_schema = connection or ConnectionSchema(
            base_url=destination.url,
            credentials={}
        )

        # Handle Assisted Connector
        if destination.connector_key == "assisted":
            step_time = datetime.now(timezone.utc).isoformat()
            test_rendition = RenditionSchema(
                title="Assisted Distribution Test Pack",
                body="Structured human-submission asset package with media and guidelines checklist.",
                media_urls=["https://assets.incubrix.test/demo_hero.png", "https://assets.incubrix.test/demo_chart.png"],
                tags=["incubrix", "assisted"]
            )
            try:
                pack: AssistPackResult = await connector.build_assist_pack(test_rendition, dest_schema)
                steps.append(CertificationStepReceipt(
                    step="assisted_mode_verification",
                    status="passed",
                    timestamp=step_time,
                    details={
                        "message": "Destination correctly configured for assisted manual workflow.",
                        "media_count": len(pack.files),
                        "caption_length": len(pack.caption),
                        "deep_link": pack.deep_link,
                        "checklist_items": len(pack.checklist)
                    }
                ))
                report.verdict = "passed"
                report.passed = True
            except Exception as exc:
                steps.append(CertificationStepReceipt(
                    step="assisted_mode_verification",
                    status="failed",
                    timestamp=step_time,
                    details={"error": str(exc)}
                ))
                report.verdict = "failed"
                report.passed = False
                report.error_message = str(exc)

            report.completed_at = datetime.now(timezone.utc).isoformat()
            report.steps = steps
            await cls._save_report_and_update_db(report, destination)
            return report

        # 1. Prepare unique certification test probe
        unique_token = f"probe_{uuid.uuid4().hex[:8]}"
        max_allowed_tags = manifest.format_limits.max_tags if hasattr(manifest, "format_limits") and manifest.format_limits else 3
        probe_tags = ["incubrix", "test", "cert"][:max_allowed_tags] if max_allowed_tags > 0 else []

        rendition = RenditionSchema(
            title=f"IncuBrix Certification Probe {unique_token}",
            body=(
                f"Automated IncuBrix publication certification test post. "
                f"Token: {unique_token}. Timestamp: {started_at}. "
                "This post will be deleted automatically within seconds."
            ),
            summary="Automated certification probe",
            tags=probe_tags,
            metadata={"cert_probe_token": unique_token}
        )

        post_id: Optional[str] = None
        live_url: Optional[str] = None
        needs_cleanup = False
        renamed_fields_detected = False

        try:
            # Step 1: Validate test rendition
            val_time = datetime.now(timezone.utc).isoformat()
            val_res = await connector.validate(rendition, dest_schema, conn_schema)
            if not val_res.ok:
                steps.append(CertificationStepReceipt(
                    step="validate_rendition",
                    status="failed",
                    timestamp=val_time,
                    details={"violations": val_res.violations}
                ))
                report.verdict = "failed"
                raise ConnectorException(
                    code=ErrorCode.DEST_SPEC_VIOLATION,
                    message=f"Rendition validation failed: {'; '.join(val_res.violations)}"
                )

            steps.append(CertificationStepReceipt(
                step="validate_rendition",
                status="passed",
                timestamp=val_time,
                details={"ok": True}
            ))

            # Step 2: Publish identifiable test post (with 429 retry-after handling)
            pub_time = datetime.now(timezone.utc).isoformat()
            pub_res: Optional[PublishResult] = None
            for attempt in range(3):
                try:
                    pub_res = await connector.publish(
                        rendition,
                        dest_schema,
                        conn_schema,
                        idempotency_key=f"cert_publish_{unique_token}"
                    )
                    break
                except ConnectorException as c_exc:
                    if c_exc.code == ErrorCode.PLATFORM_RATE_LIMIT and attempt < 2:
                        wait_sec = min(int(c_exc.details.get("retry_after", 3)), 15)
                        logger.warning(f"Certification publish encountered 429. Waiting {wait_sec}s...")
                        await asyncio.sleep(wait_sec)
                        continue
                    raise

            needs_cleanup = True

            # Check for renamed response fields or missing mandatory schema items
            if not pub_res or not pub_res.platform_post_id or not isinstance(pub_res.platform_post_id, str):
                renamed_fields_detected = True
                steps.append(CertificationStepReceipt(
                    step="publish_test_post",
                    status="failed",
                    timestamp=pub_time,
                    details={"error": "Platform renamed or omitted required platform_post_id response field"}
                ))
                report.verdict = "failed"
                raise ConnectorException(
                    code=ErrorCode.DEST_SPEC_VIOLATION,
                    message="Platform response field renamed or missing (expected platform_post_id)"
                )

            post_id = pub_res.platform_post_id
            live_url = pub_res.live_url
            report.platform_post_id = post_id
            report.live_url = live_url

            steps.append(CertificationStepReceipt(
                step="publish_test_post",
                status="passed",
                timestamp=pub_time,
                details={"platform_post_id": post_id, "live_url": live_url, "status": pub_res.status}
            ))

            # Step 3 & 4: Fetch status and confirm live visibility
            status_time = datetime.now(timezone.utc).isoformat()
            status_res: Optional[StatusResult] = None
            for attempt in range(3):
                try:
                    status_res = await connector.get_status(post_id, conn_schema)
                    break
                except ConnectorException as c_exc:
                    if c_exc.code == ErrorCode.PLATFORM_RATE_LIMIT and attempt < 2:
                        wait_sec = min(int(c_exc.details.get("retry_after", 3)), 15)
                        await asyncio.sleep(wait_sec)
                        continue
                    raise

            if not status_res or (status_res.status != "published" and not status_res.live_url):
                steps.append(CertificationStepReceipt(
                    step="verify_visibility",
                    status="failed",
                    timestamp=status_time,
                    details={"status": getattr(status_res, "status", "unknown")}
                ))
                report.verdict = "failed"
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message=f"Post visibility confirmation failed with status: {getattr(status_res, 'status', 'unknown')}"
                )

            steps.append(CertificationStepReceipt(
                step="verify_visibility",
                status="passed",
                timestamp=status_time,
                details={"status": status_res.status, "verified_live_url": status_res.live_url}
            ))

            # Step 5: Delete test post
            del_time = datetime.now(timezone.utc).isoformat()
            del_res: Optional[DeleteResult] = None
            for attempt in range(3):
                try:
                    del_res = await connector.delete(post_id, conn_schema)
                    break
                except ConnectorException as c_exc:
                    if c_exc.code == ErrorCode.PLATFORM_RATE_LIMIT and attempt < 2:
                        wait_sec = min(int(c_exc.details.get("retry_after", 3)), 15)
                        await asyncio.sleep(wait_sec)
                        continue
                    raise

            if not del_res or not del_res.deleted:
                steps.append(CertificationStepReceipt(
                    step="delete_test_post",
                    status="failed",
                    timestamp=del_time,
                    details={"deleted": False}
                ))
                report.verdict = "failed"
                raise ConnectorException(
                    code=ErrorCode.PLATFORM_UNAVAILABLE,
                    message="Connector delete returned deleted=False"
                )

            steps.append(CertificationStepReceipt(
                step="delete_test_post",
                status="passed",
                timestamp=del_time,
                details={"deleted": True}
            ))

            # Step 6: Confirm deletion with subsequent read
            confirm_time = datetime.now(timezone.utc).isoformat()
            post_status_after = await connector.get_status(post_id, conn_schema)
            deletion_verified = (
                post_status_after.status in ("not_found", "deleted") or
                post_status_after.live_url == ""
            )

            # Never report deletion_confirmed=True unless proven gone
            if deletion_verified:
                report.deletion_confirmed = True
                steps.append(CertificationStepReceipt(
                    step="confirm_deletion",
                    status="passed",
                    timestamp=confirm_time,
                    details={"post_status_after": post_status_after.status, "deletion_verified": True}
                ))
                report.verdict = "passed"
                report.passed = True
                needs_cleanup = False
            else:
                report.deletion_confirmed = False
                steps.append(CertificationStepReceipt(
                    step="confirm_deletion",
                    status="failed",
                    timestamp=confirm_time,
                    details={"post_status_after": post_status_after.status, "deletion_verified": False}
                ))
                report.verdict = "failed"
                report.passed = False

        except ConnectorException as exc:
            report.passed = False
            report.error_message = exc.message
            if exc.code == ErrorCode.CONNECTION_AUTH_EXPIRED or exc.code == ErrorCode.PLATFORM_RATE_LIMIT:
                report.verdict = "inconclusive"
            else:
                report.verdict = "failed"
            logger.error(f"Certification error for {dest_schema.name}: [{exc.code.value}] {exc.message}")

        except Exception as exc:
            report.passed = False
            report.error_message = str(exc)
            if renamed_fields_detected:
                report.verdict = "failed"
            else:
                report.verdict = "inconclusive"
            logger.error(f"Certification unexpected failure for {dest_schema.name}: {str(exc)}")

        finally:
            # Mandatory Cleanup: Always clean up if probe was created and deletion not yet confirmed
            if needs_cleanup:
                logger.info(f"Initiating mandatory cleanup for probe post '{post_id}' on {dest_schema.name}...")
                cleaned = await cls._execute_guaranteed_cleanup(connector, post_id, rendition, dest_schema, conn_schema)
                steps.append(CertificationStepReceipt(
                    step="mandatory_cleanup",
                    status="passed" if cleaned else "failed",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    details={"post_id": post_id, "cleaned": cleaned}
                ))

        report.completed_at = datetime.now(timezone.utc).isoformat()
        report.steps = steps

        # Save evidence and update database status
        await cls._save_report_and_update_db(report, destination)
        return report

    @classmethod
    async def _execute_guaranteed_cleanup(
        cls,
        connector,
        post_id: Optional[str],
        rendition: RenditionSchema,
        dest_schema: DestinationSchema,
        conn_schema: ConnectionSchema,
        timeout_seconds: int = 10
    ) -> bool:
        """Retry deletion until verified gone or timeout expires."""
        target_id = post_id
        if not target_id:
            try:
                rec = await connector.reconcile(rendition, dest_schema, conn_schema, "cleanup")
                if rec:
                    target_id = rec.platform_post_id
            except Exception:
                pass

        if not target_id:
            return True

        start_time = time.time()
        delay = 0.5
        while time.time() - start_time < timeout_seconds:
            try:
                del_res = await connector.delete(target_id, conn_schema)
                stat = await connector.get_status(target_id, conn_schema)
                if stat.status in ("not_found", "deleted") or not stat.live_url:
                    logger.info(f"Guaranteed cleanup confirmed post '{target_id}' is deleted.")
                    return True
            except Exception as exc:
                logger.warning(f"Cleanup retry for {target_id} failed: {exc}")
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 5.0)

        return False

    @classmethod
    async def _save_report_and_update_db(
        cls,
        report: CertificationReport,
        destination: DestinationModel
    ):
        """Save JSON & TXT evidence and update destination status/certification record in database."""
        evidence_dict = report.model_dump()
        evidence_path = evidence_storage.save_evidence(report.certification_id, evidence_dict)
        report.evidence_file = evidence_path

        async with AsyncSessionLocal() as session:
            record = CertificationRecordModel(
                id=report.certification_id,
                destination_id=destination.id,
                connector_key=destination.connector_key,
                environment=report.environment,
                passed=report.passed,
                evidence_json=evidence_dict,
                error_message=report.error_message
            )
            session.add(record)

            dest_model = await session.get(DestinationModel, destination.id)
            if dest_model:
                if report.verdict == "passed":
                    dest_model.last_certified_at = datetime.now(timezone.utc)
                    dest_model.status = "active"
                elif report.verdict == "failed":
                    # Demote destination on certification failure or renamed response fields
                    dest_model.status = "demoted"
                    logger.warning(f"Destination '{dest_model.name}' has been demoted due to certification failure.")

            await session.commit()


harness = CertificationHarness()
