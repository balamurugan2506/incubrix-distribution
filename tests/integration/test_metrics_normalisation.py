"""Integration test verifying Metrics normalization across connectors (Outstanding Level 2).

Proves fetch_metrics works on at least three connectors:
- Dev.to
- Discourse
- Mailchimp
Normalised to: views, likes, comments, shares, clicks.
"""

import pytest
from httpx import ASGITransport
import httpx

from app.connectors.registry import registry
from app.schemas.connector import ConnectionSchema, RenditionSchema, DestinationSchema
from mock_platforms.server import mock_app


@pytest.mark.anyio
async def test_metrics_normalisation_devto_discourse_mailchimp(monkeypatch):
    """Verify that fetch_metrics normalises platform statistics into standard MetricsResult fields."""
    orig_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: orig_client(transport=ASGITransport(app=mock_app), base_url="http://mock-platforms:8000")
    )

    # 1. Dev.to Connector Metrics
    devto_conn = registry.get_connector("devto")
    devto_connection = ConnectionSchema(
        base_url="http://mock-platforms:8000/devto",
        credentials={"api_key": "mock_devto_key"}
    )
    # First publish an article to mock Dev.to
    devto_dest = DestinationSchema(
        id="d1", name="Dev.to", url="http://mock-platforms:8000/devto",
        platform_key="devto", connector_key="devto", surface="main"
    )
    devto_rendition = RenditionSchema(
        title="Metrics Test Dev.to Article",
        body="Content for metrics testing on Dev.to platform."
    )
    devto_pub = await devto_conn.publish(devto_rendition, devto_dest, devto_connection, "idemp_metrics_devto")
    devto_metrics = await devto_conn.fetch_metrics(devto_pub.platform_post_id, devto_connection)

    assert devto_metrics.views == 42
    assert devto_metrics.likes == 8
    assert devto_metrics.comments == 3
    assert isinstance(devto_metrics.shares, int)
    assert isinstance(devto_metrics.clicks, int)

    # 2. Discourse Connector Metrics
    discourse_conn = registry.get_connector("discourse")
    discourse_connection = ConnectionSchema(
        base_url="http://mock-platforms:8000/discourse",
        credentials={"api_key": "mock_key", "api_username": "mock_user"}
    )
    discourse_dest = DestinationSchema(
        id="d2", name="Discourse", url="http://mock-platforms:8000/discourse",
        platform_key="discourse", connector_key="discourse", surface="topic",
        instance_config={"category_id": 1}
    )
    discourse_rendition = RenditionSchema(
        title="Metrics Test Discourse Topic",
        body="This is a test topic for discourse metrics verification with 20+ chars."
    )
    disc_pub = await discourse_conn.publish(discourse_rendition, discourse_dest, discourse_connection, "idemp_metrics_disc")
    disc_metrics = await discourse_conn.fetch_metrics(disc_pub.platform_post_id, discourse_connection)

    assert disc_metrics.views == 25
    assert disc_metrics.likes == 5
    assert disc_metrics.comments == 2
    assert disc_metrics.shares == 0
    assert disc_metrics.clicks == 0

    # 3. Mailchimp Connector Metrics
    mailchimp_conn = registry.get_connector("mailchimp")
    mailchimp_connection = ConnectionSchema(
        base_url="http://mock-platforms:8000/mailchimp",
        credentials={"api_key": "mock_mc_key"}
    )
    mailchimp_dest = DestinationSchema(
        id="d3", name="Mailchimp Newsletter", url="http://mock-platforms:8000/mailchimp",
        platform_key="mailchimp", connector_key="mailchimp", surface="campaign"
    )
    mailchimp_rendition = RenditionSchema(
        title="Weekly Creator Newsletter",
        body="<p>Summary of this week's AI video tools and creator growth strategies.</p>"
    )
    mc_pub = await mailchimp_conn.publish(mailchimp_rendition, mailchimp_dest, mailchimp_connection, "idemp_metrics_mc")
    mc_metrics = await mailchimp_conn.fetch_metrics(mc_pub.platform_post_id, mailchimp_connection)

    assert mc_metrics.views == 15   # Unique opens normalized to views
    assert mc_metrics.clicks == 5  # Unique subscriber clicks
    assert mc_metrics.shares == 1  # Social shares
    assert isinstance(mc_metrics.likes, int)
    assert isinstance(mc_metrics.comments, int)
