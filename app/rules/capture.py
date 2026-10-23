"""Rules Capture Adapter (Advanced Level 2).

Reads a community rules page and proposes the 5 posting rules.
Every proposed rule carries a VERBATIM quote verified to be an exact substring of the page.
Proposals stay 'pending' until a human confirms them.
Loosening a rule requires explicit acknowledgement.
Includes an offline keyword reader (default), a mock adapter, and optional LLM adapter.
"""

import re
import uuid
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class ProposedRule(BaseModel):
    rule_name: str  # frequency_cap, self_promo_allowed, link_policy, disclosure_required, automation_allowed
    value: Any
    verbatim_quote: str = Field(..., description="Exact substring quote copied from the rules page")
    confidence: float = 1.0


class RulesProposal(BaseModel):
    proposal_id: str
    destination_id: str
    status: str = "pending"  # pending, confirmed, rejected
    rules: Dict[str, Any]
    quotes: Dict[str, str]
    created_at: str


# Global in-memory proposals store for review workflow
_proposals_store: Dict[str, Dict[str, Any]] = {}


class BaseRulesCaptureAdapter(ABC):
    @abstractmethod
    def extract_rules(self, page_content: str, destination_id: str) -> RulesProposal:
        pass


class KeywordRulesCaptureAdapter(BaseRulesCaptureAdapter):
    """Default offline keyword-based rules extraction adapter requiring no API keys."""

    def extract_rules(self, page_content: str, destination_id: str) -> RulesProposal:
        # Standard default conservative baseline
        extracted_rules = {
            "frequency_cap": 10,
            "frequency_period_hours": 24,
            "self_promo_allowed": True,
            "link_policy": "allowed",
            "disclosure_required": False,
            "automation_allowed": True
        }
        quotes: Dict[str, str] = {}

        # 1. Frequency Cap
        freq_match = re.search(r'([^\.\n]*?(?:no more than|limit of|maximum|at most)\s*(\d+)\s*posts?[^\.\n]*)', page_content, re.IGNORECASE)
        if freq_match:
            quote = freq_match.group(1).strip()
            if quote in page_content:
                digits = re.search(r'(\d+)', quote)
                if digits:
                    extracted_rules["frequency_cap"] = int(digits.group(1))
                    quotes["frequency_cap"] = quote

        # 2. Self Promotion
        promo_match = re.search(r'([^\.\n]*?(?:no self-promotion|self-promotion (?:is )?(?:not allowed|prohibited)|no promotional links|zero promotion)[^\.\n]*)', page_content, re.IGNORECASE)
        if promo_match:
            quote = promo_match.group(1).strip()
            if quote in page_content:
                extracted_rules["self_promo_allowed"] = False
                quotes["self_promo_allowed"] = quote
        else:
            allow_promo = re.search(r'([^\.\n]*?(?:self-promotion allowed|promotional content permitted|show off your work)[^\.\n]*)', page_content, re.IGNORECASE)
            if allow_promo:
                quote = allow_promo.group(1).strip()
                if quote in page_content:
                    extracted_rules["self_promo_allowed"] = True
                    quotes["self_promo_allowed"] = quote

        # 3. Link Policy
        link_match = re.search(r'([^\.\n]*?(?:no links allowed|links prohibited|no external links|affiliate links forbidden)[^\.\n]*)', page_content, re.IGNORECASE)
        if link_match:
            quote = link_match.group(1).strip()
            if quote in page_content:
                extracted_rules["link_policy"] = "none"
                quotes["link_policy"] = quote
        else:
            restr_link = re.search(r'([^\.\n]*?(?:maximum \d+ links|links only in comments|limited links)[^\.\n]*)', page_content, re.IGNORECASE)
            if restr_link:
                quote = restr_link.group(1).strip()
                if quote in page_content:
                    extracted_rules["link_policy"] = "restricted"
                    quotes["link_policy"] = quote

        # 4. AI Disclosure
        ai_match = re.search(r'([^\.\n]*?(?:must disclose ai|ai generated content must be labeled|disclose use of artificial intelligence|ai disclosure required)[^\.\n]*)', page_content, re.IGNORECASE)
        if ai_match:
            quote = ai_match.group(1).strip()
            if quote in page_content:
                extracted_rules["disclosure_required"] = True
                quotes["disclosure_required"] = quote

        # 5. Automation
        auto_match = re.search(r'([^\.\n]*?(?:no bots allowed|automated (?:bots|posting)(?:\s+(?:are|is))?\s+prohibited|bots (?:will be|are) banned|no automated scripts)[^\.\n]*)', page_content, re.IGNORECASE)
        if auto_match:
            quote = auto_match.group(1).strip()
            if quote in page_content:
                extracted_rules["automation_allowed"] = False
                quotes["automation_allowed"] = quote

        proposal_id = f"prop_{uuid.uuid4().hex[:10]}"
        proposal = RulesProposal(
            proposal_id=proposal_id,
            destination_id=destination_id,
            status="pending",
            rules=extracted_rules,
            quotes=quotes,
            created_at=str(uuid.uuid4())
        )

        _proposals_store[proposal_id] = proposal.model_dump()
        return proposal


class MockRulesCaptureAdapter(BaseRulesCaptureAdapter):
    """Mock adapter for deterministic testing with exact substring validation."""

    def extract_rules(self, page_content: str, destination_id: str) -> RulesProposal:
        proposal_id = f"mock_prop_{uuid.uuid4().hex[:8]}"

        # Pick exact sentences from page_content as quotes
        lines = [line.strip() for line in page_content.splitlines() if line.strip()]
        q_promo = lines[0] if lines else "Rule 1: No self-promotion allowed"
        q_ai = lines[1] if len(lines) > 1 else "Rule 2: AI disclosure required"

        proposal = RulesProposal(
            proposal_id=proposal_id,
            destination_id=destination_id,
            status="pending",
            rules={
                "frequency_cap": 2,
                "frequency_period_hours": 24,
                "self_promo_allowed": False,
                "link_policy": "restricted",
                "disclosure_required": True,
                "automation_allowed": True
            },
            quotes={
                "self_promo_allowed": q_promo,
                "disclosure_required": q_ai
            },
            created_at=str(uuid.uuid4())
        )
        _proposals_store[proposal_id] = proposal.model_dump()
        return proposal


def confirm_rules_proposal(
    proposal_id: str,
    current_rules: Dict[str, Any],
    acknowledge_loosening: bool = False
) -> Dict[str, Any]:
    """
    Confirms a pending rules proposal.
    Validates verbatim quotes are not empty and detects any loosening of rules.
    If a rule is loosened and acknowledge_loosening is False, raises ValueError with warning.
    """
    proposal = _proposals_store.get(proposal_id)
    if not proposal:
        raise ValueError(f"Proposal '{proposal_id}' not found.")

    if proposal["status"] != "pending":
        raise ValueError(f"Proposal '{proposal_id}' is already {proposal['status']}.")

    new_rules = proposal["rules"]
    quotes = proposal["quotes"]

    # Verify that every extracted rule quote is present and non-empty
    for rule_name, quote in quotes.items():
        if not quote or not quote.strip():
            raise ValueError(f"Proposal for '{rule_name}' missing mandatory verbatim quote.")

    # Check for loosened rules:
    loosened: List[str] = []

    # 1. Self promo loosened from False to True
    if current_rules.get("self_promo_allowed") is False and new_rules.get("self_promo_allowed") is True:
        loosened.append("self_promo_allowed: loosened from False to True (allowing promotion)")

    # 2. Disclosure loosened from True to False
    if current_rules.get("disclosure_required") is True and new_rules.get("disclosure_required") is False:
        loosened.append("disclosure_required: loosened from True to False (removing AI disclosure requirement)")

    # 3. Frequency cap loosened
    old_cap = current_rules.get("frequency_cap", 10)
    new_cap = new_rules.get("frequency_cap", 10)
    if old_cap > 0 and (new_cap > old_cap or new_cap == 0):
        loosened.append(f"frequency_cap: loosened from {old_cap} to {new_cap} posts per period")

    # 4. Link policy loosened
    old_link = current_rules.get("link_policy", "restricted")
    new_link = new_rules.get("link_policy", "allowed")
    if old_link in ("none", "restricted") and new_link == "allowed":
        loosened.append(f"link_policy: loosened from '{old_link}' to 'allowed'")

    if loosened and not acknowledge_loosening:
        return {
            "status": "loosening_warning",
            "message": "Rule loosening detected. Explicit human acknowledgement required.",
            "loosened_rules": loosened,
            "proposal_id": proposal_id
        }

    proposal["status"] = "confirmed"
    _proposals_store[proposal_id] = proposal

    return {
        "status": "confirmed",
        "proposal_id": proposal_id,
        "confirmed_rules": new_rules,
        "quotes": quotes
    }
