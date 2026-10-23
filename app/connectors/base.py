"""Abstract Base Connector interface defining pure runtime connector contract."""

from abc import ABC, abstractmethod
from typing import Optional
from app.schemas.connector import (
    RenditionSchema,
    DestinationSchema,
    ConnectionSchema,
    ValidateResult,
    PublishResult,
    StatusResult,
    DeleteResult,
    MetricsResult,
    RefreshAuthResult,
    AssistPackResult
)
from app.rules.errors import ConnectorException, ErrorCode


class BaseConnector(ABC):
    """
    Pure connector runtime interface.
    Connector methods must only interact with external platform endpoints
    and return typed result objects; they must not access IncuBrix's database directly.
    """

    key: str

    @abstractmethod
    async def validate(
        self,
        rendition: RenditionSchema,
        destination: DestinationSchema,
        connection: ConnectionSchema
    ) -> ValidateResult:
        """Validate whether the rendition complies with platform and destination rules."""
        pass

    @abstractmethod
    async def publish(
        self,
        rendition: RenditionSchema,
        destination: DestinationSchema,
        connection: ConnectionSchema,
        idempotency_key: str
    ) -> PublishResult:
        """Publish rendition to target destination with idempotency guarantee where supported."""
        pass

    @abstractmethod
    async def get_status(
        self,
        platform_post_id: str,
        connection: ConnectionSchema
    ) -> StatusResult:
        """Fetch current publication status and verified live URL."""
        pass

    @abstractmethod
    async def delete(
        self,
        platform_post_id: str,
        connection: ConnectionSchema
    ) -> DeleteResult:
        """Delete previously published post from destination."""
        pass

    async def reconcile(
        self,
        rendition: RenditionSchema,
        destination: DestinationSchema,
        connection: ConnectionSchema,
        idempotency_key: str
    ) -> Optional[PublishResult]:
        """
        Reconcile unknown outcome by querying the platform (by title, token, or idempotency key).
        Returns PublishResult if post already exists on the destination, or None if not found.
        """
        return None

    async def fetch_metrics(
        self,
        platform_post_id: str,
        connection: ConnectionSchema,
        since: Optional[str] = None
    ) -> MetricsResult:
        """Optional: Fetch engagement metrics for a published post."""
        return MetricsResult()

    async def refresh_auth(
        self,
        connection: ConnectionSchema
    ) -> RefreshAuthResult:
        """Optional: Refresh an expiring OAuth / session token."""
        raise ConnectorException(
            code=ErrorCode.DEST_SPEC_VIOLATION,
            message=f"Connector {self.key} does not support refresh_auth",
            retryable=False,
            status_code=400
        )

    async def build_assist_pack(
        self,
        rendition: RenditionSchema,
        destination: DestinationSchema
    ) -> AssistPackResult:
        """Optional/Assisted: Build manual posting assistance package."""
        raise ConnectorException(
            code=ErrorCode.DEST_SPEC_VIOLATION,
            message=f"Connector {self.key} does not support build_assist_pack",
            retryable=False,
            status_code=400
        )
