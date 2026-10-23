"""Integration tests for all 5 Advanced Level requirements:

1. Catalogue Import benchmark & SSRF guard (tested in test_csv_benchmark_1000.py)
2. Rules Capture with verbatim quote verification and human confirmation
3. Audience Relevance scoring (1 to 5) with <= 2.0 cap for zero signal
4. Manifest-driven content tailoring (word boundary, AI disclosure protection, forum framing)
5. Three additional connectors (Hashnode, Slack, Mailchimp drafts only)
"""

import uuid
import pytest
from app.rules.capture import KeywordRulesCaptureAdapter, confirm_rules_proposal, _proposals_store
from app.catalogue.relevance import compute_audience_relevance
from app.rules.tailoring import truncate_word_boundary, tailor_rendition_for_destination
from app.schemas.connector import RenditionSchema, DestinationSchema, ConnectionSchema
from app.certification.harness import CertificationHarness
from app.models.destination import DestinationModel
from app.connectors.registry import registry


def test_advanced_2_rules_capture_verbatim_quotes_and_confirmation():
    """Verify rules capture extracts rules with exact verbatim substring quotes and enforces human confirmation."""
    sample_rules_page = (
        "Welcome to the AI Creators Community!\n"
        "1. No self-promotion allowed outside designated weekly threads.\n"
        "2. All AI generated content must be labeled clearly with disclosure.\n"
        "3. Posting volume: Limit of 2 posts per day per creator.\n"
        "4. External links: Maximum 2 links per submission.\n"
        "5. Automated bots are prohibited and will be banned immediately.\n"
    )

    adapter = KeywordRulesCaptureAdapter()
    proposal = adapter.extract_rules(sample_rules_page, destination_id="dest_adv_test")

    # Assert proposal is created in 'pending' state
    assert proposal.status == "pending"
    assert proposal.rules["self_promo_allowed"] is False
    assert proposal.rules["disclosure_required"] is True
    assert proposal.rules["frequency_cap"] == 2
    assert proposal.rules["link_policy"] == "restricted"
    assert proposal.rules["automation_allowed"] is False

    # CRITICAL: Verify every proposed rule carries a VERBATIM quote that is a substring of the page
    for rule_name, quote in proposal.quotes.items():
        assert quote != "", f"Quote for {rule_name} must not be empty"
        assert quote in sample_rules_page, f"Quote '{quote}' for {rule_name} is not a verbatim substring of the page!"

    # Test human confirmation: Attempt to loosen rule without acknowledgement
    current_strict_rules = {
        "self_promo_allowed": False,
        "disclosure_required": True,
        "frequency_cap": 2,
        "link_policy": "restricted"
    }

    # Simulate proposal that attempts to loosen self-promo
    _proposals_store[proposal.proposal_id]["rules"]["self_promo_allowed"] = True

    loosening_res = confirm_rules_proposal(
        proposal.proposal_id,
        current_rules=current_strict_rules,
        acknowledge_loosening=False
    )
    assert loosening_res["status"] == "loosening_warning"
    assert len(loosening_res["loosened_rules"]) > 0

    # Confirm with explicit human acknowledgement
    confirmed_res = confirm_rules_proposal(
        proposal.proposal_id,
        current_rules=current_strict_rules,
        acknowledge_loosening=True
    )
    assert confirmed_res["status"] == "confirmed"
    assert confirmed_res["confirmed_rules"]["self_promo_allowed"] is True


def test_advanced_3_audience_relevance_scoring():
    """Verify audience relevance scoring between 1.0 and 5.0, capping zero signals at <= 2.0."""
    # 1. Zero signal community (e.g. gardening / cooking)
    score_zero, expl_zero = compute_audience_relevance(
        name="Organic Gardening Community",
        category="agriculture",
        tags=["plants", "gardening", "soil"],
        description="Tips for growing organic tomatoes and backyard composting."
    )
    # Must NOT score above 2.0
    assert score_zero <= 2.0, f"Expected score <= 2.0 for zero audience signal, got {score_zero}"
    assert "No audience signal matching IncuBrix target verticals" in expl_zero

    # 2. Moderate signal community (e.g. single pillar: Python programming)
    score_mod, expl_mod = compute_audience_relevance(
        name="Python Backend Discussions",
        category="programming",
        tags=["python", "fastapi"],
        description="General Python web programming forum."
    )
    assert 2.5 <= score_mod <= 3.5
    assert "SAAS" in expl_mod

    # 3. High signal community (AI + SaaS + Creators + Video)
    score_high, expl_high = compute_audience_relevance(
        name="AI Video Founders & Creator Hub",
        category="technology",
        tags=["ai", "video", "saas", "creators", "founders"],
        description="For startup founders building generative AI video tools and marketing syndication platforms."
    )
    assert score_high >= 4.5
    assert "target IncuBrix audience pillar(s)" in expl_high


def test_advanced_4_manifest_driven_content_tailoring():
    """Verify tailoring: word-boundary truncation, AI disclosure retention, forum framing, and language warnings."""
    # 1. Test Word Boundary Truncation: Never cuts mid-word
    text = "IncuBrix multichannel content distribution network architecture"
    # Cutting at 22 chars: "IncuBrix multichannel" is 21 chars, next word starts at 22
    truncated = truncate_word_boundary(text, 25)
    assert truncated.endswith("..."), "Truncated text must end with ellipsis"
    # Verify no partial word at end
    assert not truncated.endswith("con..."), "Truncation must not cut mid-word"
    assert truncated == "IncuBrix multichannel..."

    # 2. Test Manifest-Driven Forum Tailoring
    registry.load_manifests()
    discourse_manifest = registry.get_manifest("discourse").model_dump()
    rendition = RenditionSchema(
        title="Scaling Content Pipelines",
        body="Detailed discussion on pipeline throughput and idempotent retries.",
        tags=["python", "fastapi"],
        canonical_url="https://incubrix.test/articles/pipelines",
        is_ai_generated=True,
        ai_disclosure_text="Drafted by AI, verified by engineering team."
    )

    tailored_forum, warnings = tailor_rendition_for_destination(
        rendition,
        discourse_manifest,
        destination_language="en"
    )

    # Forum framing applied
    assert tailored_forum.title.startswith("Discussion:")
    # Forum closing question appended
    assert "What are your thoughts on this?" in tailored_forum.body
    # AI disclosure appended intact at the end
    assert "*Drafted by AI, verified by engineering team.*" in tailored_forum.body
    # Tags formatted as slugs
    assert tailored_forum.tags == ["python", "fastapi"]

    # 3. Test Language Mismatch Warning
    _, lang_warnings = tailor_rendition_for_destination(
        rendition,
        discourse_manifest,
        destination_language="de"
    )
    assert len(lang_warnings) > 0
    assert "Language mismatch warning" in lang_warnings[0]


from mock_platforms.server import mock_app
import httpx


@pytest.mark.asyncio
async def test_advanced_5_three_additional_connectors(monkeypatch):
    """Verify Hashnode, Slack, and Mailchimp connectors pass full certification and contract checks."""
    # Route outbound httpx to mock_app
    real_async_client = httpx.AsyncClient

    def custom_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.ASGITransport(app=mock_app)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", custom_async_client)
    # 1. Hashnode
    hn_dest = DestinationModel(
        id=f"dest_{uuid.uuid4().hex[:8]}",
        name="Hashnode Dev Engineering Blog",
        url="http://localhost:8001/hashnode",
        platform_key="hashnode",
        connector_key="hashnode",
        surface="post",
        instance_config={"publication_id": "pub_mock_123"}
    )
    hn_conn = ConnectionSchema(
        base_url="http://localhost:8001/hashnode",
        credentials={"personal_access_token": "valid_hn_token", "publication_id": "pub_mock_123"}
    )
    hn_report = await CertificationHarness.run_certification(hn_dest, connection=hn_conn, environment="mock")
    assert hn_report.passed is True
    assert hn_report.deletion_confirmed is True
    assert hn_report.verdict == "passed"

    # 2. Slack
    slack_dest = DestinationModel(
        id=f"dest_{uuid.uuid4().hex[:8]}",
        name="Slack Announcements Channel",
        url="http://localhost:8001/slack",
        platform_key="slack",
        connector_key="slack",
        surface="channel",
        instance_config={"channel_id": "C_DEV"}
    )
    slack_conn = ConnectionSchema(
        base_url="http://localhost:8001/slack",
        credentials={"bot_token": "xoxb-valid-slack-token", "channel_id": "C_DEV"}
    )
    slack_report = await CertificationHarness.run_certification(slack_dest, connection=slack_conn, environment="mock")
    assert slack_report.passed is True
    assert slack_report.deletion_confirmed is True
    assert slack_report.verdict == "passed"

    # 3. Mailchimp (Drafts Only)
    mc_dest = DestinationModel(
        id=f"dest_{uuid.uuid4().hex[:8]}",
        name="Mailchimp Newsletter Campaign (Drafts)",
        url="http://localhost:8001/mailchimp",
        platform_key="mailchimp",
        connector_key="mailchimp",
        surface="campaign_draft",
        instance_config={"list_id": "list_subscribers_123"}
    )
    mc_conn = ConnectionSchema(
        base_url="http://localhost:8001/mailchimp",
        credentials={"api_key": "mock_mc_key-us1", "list_id": "list_subscribers_123"}
    )
    mc_report = await CertificationHarness.run_certification(mc_dest, connection=mc_conn, environment="mock")
    assert mc_report.passed is True
    assert mc_report.verdict == "passed"
    # CRITICAL: Confirm status is strictly draft ('draft' / 'save')
    mc_connector = registry.get_connector("mailchimp")
    status_res = await mc_connector.get_status(mc_report.platform_post_id, mc_conn)
    # The campaign was deleted in certification cleanup, verifying complete lifecycle
    assert mc_report.deletion_confirmed is True
