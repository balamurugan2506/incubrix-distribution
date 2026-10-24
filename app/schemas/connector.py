"""Pydantic schemas defining the connector contract models and payload shapes."""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class RenditionSchema(BaseModel):
    title: Optional[str] = Field(None, description="Title or headline of the rendition")
    body: str = Field(..., description="Main text body (markdown, HTML, or plain text)")
    summary: Optional[str] = Field(None, description="Short excerpt or description")
    tags: List[str] = Field(default_factory=list, description="Keywords or hashtags")
    media_urls: List[str] = Field(default_factory=list, description="Associated image, video, or asset URLs")
    canonical_url: Optional[str] = Field(None, description="Original canonical source URL")
    is_ai_generated: bool = Field(False, description="Flag indicating if content was AI-generated")
    ai_disclosure_text: Optional[str] = Field(None, description="Explicit statement of AI disclosure if required")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom platform-specific parameters")


class DestinationSchema(BaseModel):
    id: Optional[str] = Field(None, description="Unique destination ID in IncuBrix catalogue")
    name: str = Field(..., description="Display name of the destination")
    url: str = Field(..., description="Destination site or community URL")
    platform_key: str = Field(..., description="Platform identifier (discourse, lemmy, devto, ghost, webhook, assisted)")
    connector_key: str = Field(..., description="Target connector key matching manifest")
    surface: Optional[str] = Field("main", description="Surface type (forum, blog, feed, webhook)")
    instance_config: Dict[str, Any] = Field(default_factory=dict, description="Platform instance settings (e.g. category_id, sub-community)")
    rules: Dict[str, Any] = Field(
        default_factory=lambda: {
            "frequency_cap": 10,
            "frequency_period_hours": 24,
            "self_promo_allowed": True,
            "link_policy": "allowed",
            "disclosure_required": False,
            "automation_allowed": True
        },
        description="Posting rules (length limits, link limits, etc.)"
    )


class ConnectionSchema(BaseModel):
    base_url: Optional[str] = Field(None, description="Base API endpoint if configurable per instance")
    credentials: Dict[str, Any] = Field(default_factory=dict, description="Credentials (api_key, token, secret, username)")
    expires_at: Optional[str] = Field(None, description="ISO timestamp of token expiry")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional connection state")


# Request Payload Wrappers for connector endpoints
class ValidateRequest(BaseModel):
    rendition: RenditionSchema
    destination: DestinationSchema
    connection: ConnectionSchema


class PublishRequest(BaseModel):
    rendition: RenditionSchema
    destination: DestinationSchema
    connection: ConnectionSchema
    idempotency_key: str = Field(..., description="Unique client idempotency key")


class StatusRequest(BaseModel):
    platform_post_id: str = Field(..., description="External platform post ID")
    connection: ConnectionSchema


class DeleteRequest(BaseModel):
    platform_post_id: str = Field(..., description="External platform post ID")
    connection: ConnectionSchema


class FetchMetricsRequest(BaseModel):
    platform_post_id: str = Field(..., description="External platform post ID")
    connection: ConnectionSchema
    since: Optional[str] = Field(None, description="ISO date filter for metrics query")


class RefreshAuthRequest(BaseModel):
    connection: ConnectionSchema


class BuildAssistPackRequest(BaseModel):
    rendition: RenditionSchema
    destination: DestinationSchema


# Exact Required Return Shapes
class ValidateResult(BaseModel):
    ok: bool
    violations: List[str] = Field(default_factory=list)


class PublishResult(BaseModel):
    platform_post_id: str
    live_url: str
    status: str = Field(..., description="Post publication state (e.g. published, draft, queued)")


class StatusResult(BaseModel):
    status: str
    live_url: str


class DeleteResult(BaseModel):
    deleted: bool


class MetricsResult(BaseModel):
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    watch_time_s: int = 0
    clicks: int = 0


class RefreshAuthResult(BaseModel):
    expires_at: str


class AssistPackResult(BaseModel):
    files: List[str] = Field(default_factory=list)
    caption: str
    deep_link: str
    checklist: List[str] = Field(default_factory=list)
    download_url: Optional[str] = None
    pack_id: Optional[str] = None

