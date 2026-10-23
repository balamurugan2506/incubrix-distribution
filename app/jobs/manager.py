"""Background Job manager and execution engine."""

import uuid
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.job import JobRecordModel
from app.models.destination import DestinationModel
from app.models.publication import PublicationRecordModel
from app.schemas.connector import RenditionSchema, DestinationSchema, ConnectionSchema
from app.connectors.registry import registry
from app.rules.engine import rules_engine
from app.rules.backoff import execute_with_retry
from app.rules.errors import ConnectorException, ErrorCode
from app.jobs.callback import dispatch_job_callback
from app.logging_conf import logger


class JobManager:
    @staticmethod
    async def create_job(
        destination_id: str,
        callback_url: Optional[str] = None
    ) -> JobRecordModel:
        """Create and persist a new publication job in queued state."""
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        async with AsyncSessionLocal() as session:
            job = JobRecordModel(
                job_id=job_id,
                destination_id=destination_id,
                status="queued",
                progress=0,
                callback_url=callback_url
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job

    @staticmethod
    async def update_job(
        job_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        result: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Update job progress and state in database."""
        async with AsyncSessionLocal() as session:
            stmt = select(JobRecordModel).where(JobRecordModel.job_id == job_id)
            res = await session.execute(stmt)
            job = res.scalar_one_or_none()
            if job:
                if status is not None:
                    job.status = status
                if progress is not None:
                    job.progress = progress
                if result is not None:
                    job.result = result
                if error_code is not None:
                    job.error_code = error_code
                if error_message is not None:
                    job.error_message = error_message
                await session.commit()

    @classmethod
    async def run_publication_job(
        cls,
        job_id: str,
        destination_id: str,
        rendition: RenditionSchema,
        connection: Optional[ConnectionSchema] = None,
        idempotency_key: Optional[str] = None,
        callback_url: Optional[str] = None
    ) -> None:
        """Asynchronously executes destination lookup, rules checks, publication, and callback."""
        idem_key = idempotency_key or f"idem_{job_id}"
        logger.info(f"Starting publication job {job_id} for destination {destination_id}")

        await cls.update_job(job_id, status="running", progress=15)

        async with AsyncSessionLocal() as session:
            stmt = select(DestinationModel).where(DestinationModel.id == destination_id)
            res = await session.execute(stmt)
            destination_model = res.scalar_one_or_none()

            if not destination_model:
                err_msg = f"Destination '{destination_id}' not found in catalogue"
                await cls.update_job(job_id, status="failed", progress=100, error_code=ErrorCode.DEST_SPEC_VIOLATION.value, error_message=err_msg)
                if callback_url:
                    await dispatch_job_callback(callback_url, job_id, "failed", error_code=ErrorCode.DEST_SPEC_VIOLATION.value, error_message=err_msg)
                return

            # Check Posting Rules
            try:
                await rules_engine.check_rules(
                    rendition=rendition,
                    destination=destination_model,
                    db=session,
                    is_automated_request=True
                )
            except ConnectorException as exc:
                logger.warning(f"Posting rule violation for job {job_id}: {exc.message}")
                await cls.update_job(job_id, status="failed", progress=100, error_code=exc.code.value, error_message=exc.message)
                if callback_url:
                    await dispatch_job_callback(callback_url, job_id, "failed", error_code=exc.code.value, error_message=exc.message)
                return

            await cls.update_job(job_id, progress=40)

            # Prepare connector schemas
            dest_schema = DestinationSchema(
                id=destination_model.id,
                name=destination_model.name,
                url=destination_model.url,
                platform_key=destination_model.platform_key,
                connector_key=destination_model.connector_key,
                surface=destination_model.surface,
                instance_config=destination_model.instance_config or {}
            )

            conn_schema = connection or ConnectionSchema(
                base_url=destination_model.url,
                credentials={}
            )

            connector = registry.get_connector(destination_model.connector_key)

            # Publish with exponential backoff & retry
            async def publish_call():
                return await connector.publish(
                    rendition=rendition,
                    destination=dest_schema,
                    connection=conn_schema,
                    idempotency_key=idem_key
                )

            try:
                await cls.update_job(job_id, progress=60)
                pub_result = await execute_with_retry(
                    publish_call,
                    operation_name=f"publish_{destination_model.connector_key}"
                )
            except ConnectorException as exc:
                logger.error(f"Connector failure for job {job_id}: [{exc.code.value}] {exc.message}")
                await cls.update_job(job_id, status="failed", progress=100, error_code=exc.code.value, error_message=exc.message)
                if callback_url:
                    await dispatch_job_callback(callback_url, job_id, "failed", error_code=exc.code.value, error_message=exc.message)
                return
            except Exception as exc:
                logger.error(f"Unexpected failure in job {job_id}: {str(exc)}")
                await cls.update_job(job_id, status="failed", progress=100, error_code=ErrorCode.PLATFORM_UNAVAILABLE.value, error_message=str(exc))
                if callback_url:
                    await dispatch_job_callback(callback_url, job_id, "failed", error_code=ErrorCode.PLATFORM_UNAVAILABLE.value, error_message=str(exc))
                return

            # Record successful publication in database
            pub_record = PublicationRecordModel(
                id=f"pub_{uuid.uuid4().hex[:12]}",
                destination_id=destination_model.id,
                platform_post_id=pub_result.platform_post_id,
                live_url=pub_result.live_url,
                status=pub_result.status,
                rendition_title=rendition.title
            )
            session.add(pub_record)
            destination_model.last_certified_at = datetime.now(timezone.utc)
            await session.commit()

            result_dict = {
                "platform_post_id": pub_result.platform_post_id,
                "live_url": pub_result.live_url,
                "status": pub_result.status,
                "destination_id": destination_model.id,
                "destination_name": destination_model.name
            }

            await cls.update_job(job_id, status="succeeded", progress=100, result=result_dict)
            logger.info(f"Job {job_id} succeeded. Live URL: {pub_result.live_url}")

            if callback_url:
                await dispatch_job_callback(callback_url, job_id, "succeeded", result=result_dict)


job_manager = JobManager()
