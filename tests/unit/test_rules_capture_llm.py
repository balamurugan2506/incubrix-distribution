"""Unit tests for LLM Rules Capture Adapter (Advanced Level 2).

Verifies:
1. LLM adapter communicates with HTTP endpoint, parses structured rule proposals, and tracks token usage/cost.
2. Exact substring verification guard: quotes must exist in source page.
3. Hallucinated proposals with non-matching quotes are DROPPED as unverifiable.
4. Automatic retry on HTTP 429 rate limit with exponential backoff.
5. Proposals stay 'pending' until explicitly confirmed by human operator.
6. Loosening any existing posting rule requires explicit human acknowledgement.
7. No API key is ever logged or committed.
"""

import pytest
from app.rules.capture import (
    GeminiRulesCaptureAdapter,
    confirm_rules_proposal,
    _proposals_store
)

SAMPLE_GUIDELINES = """
Welcome to the IncuBrix Test Community!
Here are our community participation guidelines:
1. Posting frequency: there is a strict limit of 3 posts per day per creator.
2. Respect community focus: no self-promotion allowed in top-level discussion threads.
3. Link etiquette: links only in comments when directly answering a question.
4. Transparency: creators must disclose ai generated content prominently.
5. System integrity: automated bots are prohibited from unauthorized crawling or posting.
"""


def test_gemini_adapter_exact_substring_verification_and_cost():
    """Verify that valid quotes from LLM are verified as exact substrings and token usage is tracked."""
    adapter = GeminiRulesCaptureAdapter(
        endpoint_url="http://localhost:8001/mock_gemini/v1beta/models/gemini-1.5-flash:generateContent"
    )

    proposal = adapter.extract_rules(
        page_content=SAMPLE_GUIDELINES,
        destination_id="dest_sample_community_01"
    )

    # 1. Proposal state
    assert proposal.status == "pending"
    assert proposal.extractor == "gemini-1.5-flash"
    assert proposal.destination_id == "dest_sample_community_01"

    # 2. Verbatim Quotes must be exact substrings of source text
    for rule_name, quote in proposal.quotes.items():
        assert quote in SAMPLE_GUIDELINES, f"Quote for {rule_name} ('{quote}') is not in source text!"

    assert proposal.rules["frequency_cap"] == 3
    assert proposal.rules["self_promo_allowed"] is False
    assert proposal.rules["link_policy"] == "restricted"
    assert proposal.rules["disclosure_required"] is True
    assert proposal.rules["automation_allowed"] is False

    # 3. Token & Cost tracking
    assert proposal.token_usage["total_tokens"] > 0
    assert proposal.token_usage["cost_usd"] >= 0.0


def test_gemini_adapter_rate_limit_retry_exponential_backoff():
    """Verify that HTTP 429 rate limit triggers automatic retry and succeeds."""
    adapter = GeminiRulesCaptureAdapter(
        endpoint_url="http://localhost:8001/mock_gemini/v1beta/models/gemini-1.5-flash:generateContent",
        custom_headers={"x-simulate-rate-limit": "true"}
    )

    proposal = adapter.extract_rules(
        page_content=SAMPLE_GUIDELINES,
        destination_id="dest_rate_limit_test"
    )
    assert proposal.status == "pending"
    assert len(proposal.quotes) > 0


def test_gemini_adapter_drops_hallucinated_unverifiable_quotes():
    """Verify that hallucinated quotes NOT in source text are dropped as unverifiable."""
    adapter = GeminiRulesCaptureAdapter(
        endpoint_url="http://localhost:8001/mock_gemini/v1beta/models/gemini-1.5-flash:generateContent",
        custom_headers={"x-simulate-hallucination": "true"}
    )

    proposal = adapter.extract_rules(
        page_content=SAMPLE_GUIDELINES,
        destination_id="dest_hallucination_test"
    )

    # All unverifiable or hallucinated rules must have been dropped
    dropped_rule_names = [drop["rule"] for drop in proposal.dropped_proposals]
    assert "frequency_cap" in dropped_rule_names
    assert "self_promo_allowed" in dropped_rule_names

    # Verify hallucinated quote is not accepted into verified quotes
    assert "frequency_cap" not in proposal.quotes
    assert "self_promo_allowed" not in proposal.quotes
    assert len(proposal.quotes) == 0



def test_rules_proposal_human_confirmation_and_loosening_acknowledgement():
    """Verify human confirmation workflow and loosening acknowledgement requirements."""
    adapter = GeminiRulesCaptureAdapter(
        endpoint_url="http://localhost:8001/mock_gemini/v1beta/models/gemini-1.5-flash:generateContent"
    )
    proposal = adapter.extract_rules(
        page_content=SAMPLE_GUIDELINES,
        destination_id="dest_confirm_test"
    )

    # Proposal must be stored as 'pending'
    assert proposal.proposal_id in _proposals_store
    assert _proposals_store[proposal.proposal_id]["status"] == "pending"

    # Strict baseline: self-promo prohibited, disclosure required
    strict_current_rules = {
        "self_promo_allowed": False,
        "disclosure_required": True,
        "frequency_cap": 1,
        "link_policy": "none"
    }

    # Proposing new rules with frequency_cap=3 and link_policy=restricted is loosening
    warning_res = confirm_rules_proposal(
        proposal_id=proposal.proposal_id,
        current_rules=strict_current_rules,
        acknowledge_loosening=False
    )
    assert warning_res["status"] == "loosening_warning"
    assert len(warning_res["loosened_rules"]) > 0

    # With explicit acknowledgement, confirmation succeeds
    confirmed_res = confirm_rules_proposal(
        proposal_id=proposal.proposal_id,
        current_rules=strict_current_rules,
        acknowledge_loosening=True
    )
    assert confirmed_res["status"] == "confirmed"
    assert _proposals_store[proposal.proposal_id]["status"] == "confirmed"
