"""Connector Registry and YAML Manifest Loader."""

import os
import yaml
from typing import Dict, Any, Type, Optional, List
from pydantic import BaseModel, Field
from app.config import settings
from app.connectors.base import BaseConnector
from app.rules.errors import ConnectorException, ErrorCode


class ManifestAuth(BaseModel):
    type: str
    header_name: Optional[str] = None
    fields: List[str] = Field(default_factory=list)


class ManifestFormatLimits(BaseModel):
    title_min_chars: int = 0
    title_max_chars: int = 1000
    body_min_chars: int = 0
    body_max_chars: int = 1000000
    max_tags: int = 10
    max_media_bytes: int = 50000000


class ManifestRateLimits(BaseModel):
    requests_per_minute: int = 60
    burst: int = 10


class ManifestCapabilities(BaseModel):
    publish: bool = True
    delete: bool = True
    get_status: bool = True
    fetch_metrics: bool = False
    refresh_auth: bool = False
    build_assist_pack: bool = False


class ConnectorManifest(BaseModel):
    key: str
    name: str
    version: str
    tier: str
    auth: ManifestAuth
    surfaces: List[str]
    content_types: List[str]
    format_limits: ManifestFormatLimits
    rate_limits: ManifestRateLimits
    capabilities: ManifestCapabilities
    instance_param: Dict[str, Any] = Field(default_factory=dict)
    error_map: Dict[int, str] = Field(default_factory=dict)


class ConnectorRegistry:
    def __init__(self, manifests_dir: Optional[str] = None):
        self.manifests_dir = manifests_dir or settings.MANIFESTS_DIR
        self._manifests: Dict[str, ConnectorManifest] = {}
        self._connector_classes: Dict[str, Type[BaseConnector]] = {}
        self._connector_instances: Dict[str, BaseConnector] = {}

    def load_manifests(self) -> None:
        """Scan and load all YAML manifests from the manifests directory."""
        if not os.path.exists(self.manifests_dir):
            return

        for filename in os.listdir(self.manifests_dir):
            if filename.endswith(".yaml") or filename.endswith(".yml"):
                filepath = os.path.join(self.manifests_dir, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    raw_data = yaml.safe_load(f)
                    manifest = ConnectorManifest(**raw_data)
                    self._manifests[manifest.key] = manifest

    def register_connector(self, connector_class: Type[BaseConnector]) -> None:
        """Register a connector implementation class."""
        self._connector_classes[connector_class.key] = connector_class

    def get_manifest(self, key: str) -> ConnectorManifest:
        """Retrieve manifest by connector key."""
        if not self._manifests:
            self.load_manifests()
        if key not in self._manifests:
            raise ConnectorException(
                code=ErrorCode.CONNECTOR_DISABLED,
                message=f"No connector manifest found for key: {key}",
                retryable=False,
                status_code=404
            )
        return self._manifests[key]

    def get_connector(self, key: str) -> BaseConnector:
        """Retrieve or instantiate connector instance."""
        if not self._manifests:
            self.load_manifests()

        if key not in self._manifests:
            raise ConnectorException(
                code=ErrorCode.CONNECTOR_DISABLED,
                message=f"Connector {key} not found or disabled in manifests",
                retryable=False,
                status_code=404
            )

        if key not in self._connector_instances:
            if key not in self._connector_classes:
                raise ConnectorException(
                    code=ErrorCode.CONNECTOR_DISABLED,
                    message=f"Connector implementation not registered for key: {key}",
                    retryable=False,
                    status_code=501
                )
            self._connector_instances[key] = self._connector_classes[key]()

        return self._connector_instances[key]

    def list_manifests(self) -> List[ConnectorManifest]:
        """List all loaded connector manifests."""
        if not self._manifests:
            self.load_manifests()
        return list(self._manifests.values())


registry = ConnectorRegistry()
