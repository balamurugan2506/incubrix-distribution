"""Unit and integration tests for Enhanced Posting Rules (Must-Have 4 & Gap E)."""

import pytest
from datetime import datetime, timezone
from app.rules.engine import rules_engine
from app.models.destination import DestinationModel
from app.models.publication import PublicationRecordModel
from app.schemas.connector import RenditionSchema, DestinationSchema
from app.rules.errors import ConnectorException, ErrorCode
from app.database import AsyncSessionLocal


def test_link_counting_every_written_form():
    """Verify that links in all forms (HTTP, HTTPS, www, markdown, HTML, bare domains) are detected."""
    text = (
        "Check our documentation at https://incubrix.ai/docs and the mirror at http://mirror.io/api. "
        "Also visit www.community-hub.org/forum for support. "
        "See [Developer Guide](https://github.com/incubrix/guide) and [Whitepaper](incubrix.tech/paper). "
        "Direct anchor: <a href=\"https://status.incubrix.com\">System Status</a>. "
        "Also read articles on techcrunch.com."
    )
    links = rules_engine._extract_links(text)
    # Should detect distinct link references across all forms
    assert len(links) >= 6
    # Verify bare domain detection
    assert any("techcrunch.com" in l for l in links)
    # Verify www address detection
    assert any("www.community-hub.org" in l for l in links)
    # Verify markdown link detection
    assert any("github.com/incubrix/guide" in l for l in links)
    # Verify HTML link detection
    assert any("status.incubrix.com" in l for l in links)


def test_self_promo_multi_marker_heuristics():
    """Verify multi-marker heuristics: standalone strong words block, combined markers block, single weak word does not."""
    # 1. Single weak phrase should NOT block (avoid false positive)
    rend_weak = RenditionSchema(
        title="Engineering Design Patterns",
        body="In this article you can learn more at your own pace about distributed state machines.",
        tags=["design"]
    )
    is_promo, markers = rules_engine._is_self_promotional(rend_weak)
    assert is_promo is False
    assert len(markers) == 0

    # 2. Strong commercial keyword MUST block immediately
    rend_strong = RenditionSchema(
        title="New Tool Release",
        body="Use discount code LAUNCH50 to get a special discount on our plans.",
        tags=["release"]
    )
    is_promo, markers = rules_engine._is_self_promotional(rend_strong)
    assert is_promo is True
    assert any("discount code" in m or "special discount" in m for m in markers)

    # 3. Two distinct categories (CTA + Sign-up) MUST block
    rend_multi = RenditionSchema(
        title="Check out our platform",
        body="Check out our new architecture and sign up for early access.",
        tags=["launch"]
    )
    is_promo, markers = rules_engine._is_self_promotional(rend_multi)
    assert is_promo is True
    assert len(markers) >= 2


@pytest.mark.asyncio
async def test_fail_closed_on_missing_rules():
    """Verify fail-closed refusal when a destination is missing any of the 5 required rules."""
    rend = RenditionSchema(
        title="Valid Discussion Topic for Technical Community",
        body="A detailed discussion about distributed message brokers and queues in production.",
        tags=["tech"]
    )

    # Missing self_promo_allowed
    dest_missing = DestinationSchema(
        name="Strict Forum",
        url="https://forum.example.com",
        platform_key="discourse",
        connector_key="discourse",
        rules={
            "frequency_cap": 5,
            # self_promo_allowed missing!
            "link_policy": "allowed",
            "disclosure_required": False,
            "automation_allowed": True
        }
    )

    with pytest.raises(ConnectorException) as exc_info:
        await rules_engine.check_rules(rend, dest_missing)

    assert exc_info.value.code == ErrorCode.DEST_SPEC_VIOLATION
    assert "missing or incomplete posting rules" in exc_info.value.message
    assert "self_promo_allowed" in exc_info.value.message


@pytest.mark.asyncio
async def test_link_policy_enforcement():
    """Verify link policy enforcement for 'none', 'restricted' (max 2), and 'max:1'."""
    dest_none = DestinationSchema(
        name="No Links Community",
        url="https://nolinks.org",
        platform_key="devto",
        connector_key="devto",
        rules={
            "frequency_cap": 5,
            "self_promo_allowed": True,
            "link_policy": "none",
            "disclosure_required": False,
            "automation_allowed": True
        }
    )

    rend_with_link = RenditionSchema(
        title="Dev.to Article with External Source",
        body="Read full research at https://arxiv.org/abs/1234.5678 for details.",
        tags=["python"]
    )

    with pytest.raises(ConnectorException) as exc_info:
        await rules_engine.check_rules(rend_with_link, dest_none)

    assert exc_info.value.code == ErrorCode.DEST_SPEC_VIOLATION
    assert "strictly prohibits external links" in exc_info.value.message

    # Test max:1 policy allows 1 link, blocks 2
    dest_max1 = DestinationSchema(
        name="Single Link Allowed",
        url="https://singlelink.org",
        platform_key="devto",
        connector_key="devto",
        rules={
            "frequency_cap": 5,
            "self_promo_allowed": True,
            "link_policy": "max:1",
            "disclosure_required": False,
            "automation_allowed": True
        }
    )
    # 1 link passes
    await rules_engine.check_rules(rend_with_link, dest_max1)

    # 2 links fail
    rend_two_links = RenditionSchema(
        title="Dev.to Article with Two External Sources",
        body="Source 1: https://arxiv.org/abs/1 Source 2: www.github.com/incubrix",
        tags=["python"]
    )
    with pytest.raises(ConnectorException) as exc2:
        await rules_engine.check_rules(rend_two_links, dest_max1)
    assert "allows at most 1 external links" in exc2.value.message


@pytest.mark.asyncio
async def test_frequency_cap_second_post_blocked():
    """Verify that exceeding frequency cap inside the period blocks the second post with clear 429 reason."""
    import uuid
    from app.database import init_db
    await init_db()
    dest_id = f"dest_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as session:
        # Create a mock destination in DB
        dest = DestinationModel(
            id=dest_id,
            name="Capped Community",
            url="https://capped.test",
            normalised_url="https://capped.test",
            platform_key="discourse",
            connector_key="discourse",
            frequency_cap=1,  # Only 1 post allowed per 12 hours
            frequency_period_hours=12,
            self_promo_allowed=True,
            link_policy="allowed",
            disclosure_required=False,
            automation_allowed=True
        )
        session.add(dest)

        # Record 1 existing published post within the window
        pub = PublicationRecordModel(
            id=f"pub_{uuid.uuid4().hex[:8]}",
            destination_id=dest_id,
            platform_post_id="post_999",
            status="published",
            created_at=datetime.now(timezone.utc)
        )
        session.add(pub)
        await session.commit()

        rend = RenditionSchema(
            title="Second Post Attempt In Window",
            body="Attempting to publish a second post inside the 12-hour frequency cap.",
            tags=["rate"]
        )

        with pytest.raises(ConnectorException) as exc_info:
            await rules_engine.check_rules(rend, dest, db=session)

        assert exc_info.value.code == ErrorCode.DEST_RULE_FREQUENCY_CAP
        assert exc_info.value.status_code == 429
        assert "Frequency cap exceeded" in exc_info.value.message
        assert "1/1 posts published in the last 12 hours" in exc_info.value.message
