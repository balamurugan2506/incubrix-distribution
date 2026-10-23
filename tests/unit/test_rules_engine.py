"""Unit tests for PostingRulesEngine policy enforcement."""

import pytest
from app.rules.engine import rules_engine
from app.models.destination import DestinationModel
from app.schemas.connector import RenditionSchema
from app.rules.errors import ConnectorException, ErrorCode


@pytest.mark.asyncio
async def test_disabled_destination_rejected():
    dest = DestinationModel(
        id="d1", name="Inactive Forum", platform_key="discourse", connector_key="discourse",
        url="http://test.local", normalised_url="http://test.local", enabled=False
    )
    rend = RenditionSchema(title="Sample Post", body="Some body text with enough length.")

    with pytest.raises(ConnectorException) as exc:
        await rules_engine.check_rules(rend, dest)
    assert exc.value.code == ErrorCode.CONNECTOR_DISABLED


@pytest.mark.asyncio
async def test_automation_not_allowed_rejected():
    dest = DestinationModel(
        id="d2", name="Substack Community", platform_key="assisted", connector_key="assisted",
        url="http://test.local", normalised_url="http://test.local", enabled=True,
        automation_allowed=False
    )
    rend = RenditionSchema(title="Sample Post", body="Some body text with enough length.")

    with pytest.raises(ConnectorException) as exc:
        await rules_engine.check_rules(rend, dest, is_automated_request=True)
    assert exc.value.code == ErrorCode.CONNECTOR_DISABLED
    assert "prohibits automated posting" in exc.value.message


@pytest.mark.asyncio
async def test_self_promo_policy():
    dest = DestinationModel(
        id="d3", name="Strict Reddit Community", platform_key="lemmy", connector_key="lemmy",
        url="http://test.local", normalised_url="http://test.local", enabled=True,
        self_promo_allowed=False
    )
    rend = RenditionSchema(
        title="Check out our product",
        body="Sign up today and use promo code INCUBRIX for 50% discount!"
    )

    with pytest.raises(ConnectorException) as exc:
        await rules_engine.check_rules(rend, dest)
    assert exc.value.code == ErrorCode.DEST_SPEC_VIOLATION
    assert "self-promotional" in exc.value.message


@pytest.mark.asyncio
async def test_link_policy_none():
    dest = DestinationModel(
        id="d4", name="Zero Link Forum", platform_key="discourse", connector_key="discourse",
        url="http://test.local", normalised_url="http://test.local", enabled=True,
        link_policy="none"
    )
    rend = RenditionSchema(
        title="Valid Discussion Title Here",
        body="Here is some text with a link: https://example.com/blog and nothing else."
    )

    with pytest.raises(ConnectorException) as exc:
        await rules_engine.check_rules(rend, dest)
    assert exc.value.code == ErrorCode.DEST_SPEC_VIOLATION
    assert "prohibits external links" in exc.value.message


@pytest.mark.asyncio
async def test_ai_disclosure_requirement():
    dest = DestinationModel(
        id="d5", name="Transparency Journal", platform_key="devto", connector_key="devto",
        url="http://test.local", normalised_url="http://test.local", enabled=True,
        disclosure_required=True
    )
    # AI generated but no disclosure text
    rend = RenditionSchema(
        title="AI Assisted Guide",
        body="Comprehensive guide about long tail network distribution models.",
        is_ai_generated=True,
        ai_disclosure_text=None
    )

    with pytest.raises(ConnectorException) as exc:
        await rules_engine.check_rules(rend, dest)
    assert exc.value.code == ErrorCode.DEST_SPEC_VIOLATION
    assert "AI-content disclosure" in exc.value.message

    # Now provide valid disclosure text
    rend.ai_disclosure_text = "This article was drafted with AI and verified by a human."
    warnings = await rules_engine.check_rules(rend, dest)
    assert warnings == []
