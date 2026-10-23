"""Manifest-Driven Content Tailoring Engine (Advanced Level 4).

Transforms and shapes content to fit target platform specifications:
- Truncates strictly at WORD boundaries (never mid-word)
- Preserves AI disclosure text intact without truncation
- Adapts discussion-first framing and closing questions for forums
- Preserves/attaches canonical URLs for article platforms
- Formats tags according to platform tag style (slug, hashtag, none)
- Issues warning on language mismatch between rendition and destination
- Strictly driven by manifest fields, avoiding hardcoded if-chains.
"""

import re
from typing import Dict, Any, List, Tuple
from app.schemas.connector import RenditionSchema


def truncate_word_boundary(text: str, max_chars: int) -> str:
    """
    Truncate text to max_chars strictly at a whitespace word boundary.
    Never cuts a word in half. Appends ellipsis if truncated.
    """
    if not text or len(text) <= max_chars:
        return text

    # Reserve 3 characters for ellipsis
    cutoff = max_chars - 3
    if cutoff <= 0:
        return "..."

    truncated = text[:cutoff]
    # Find last whitespace in the truncated slice
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]

    # Clean trailing punctuation before adding ellipsis
    truncated = truncated.rstrip(" ,;:-.\n\t") + "..."
    return truncated


def tailor_rendition_for_destination(
    rendition: RenditionSchema,
    manifest: Dict[str, Any],
    destination_language: str = "en"
) -> Tuple[RenditionSchema, List[str]]:
    """
    Tailors rendition content using parameters specified in the connector manifest.
    Returns: (tailored_rendition, warnings)
    """
    warnings: List[str] = []
    tailoring_rules = manifest.get("tailoring", {})
    format_limits = manifest.get("format_limits", {})

    max_title_chars = format_limits.get("title_max_chars", 255)
    max_body_chars = format_limits.get("body_max_chars", 65535)
    framing = tailoring_rules.get("framing", "standard")
    closing_question = tailoring_rules.get("closing_question", False)
    attach_canonical = tailoring_rules.get("attach_canonical_url", False)
    tag_style = tailoring_rules.get("tag_style", "slug")
    max_tags = format_limits.get("max_tags", 10)

    # 1. Check Language Mismatch
    rend_lang = rendition.metadata.get("language", "en")
    if destination_language and rend_lang.lower() != destination_language.lower():
        warnings.append(
            f"Language mismatch warning: Rendition language is '{rend_lang}' but destination requires '{destination_language}'."
        )

    # 2. Tailor Title
    tailored_title = rendition.title
    if tailored_title:
        # Discussion framing for forum titles if not already a question/discussion
        if framing == "discussion_first" and not any(tailored_title.lower().startswith(p) for p in ["discussion:", "question:", "how", "what", "why"]):
            tailored_title = f"Discussion: {tailored_title}"

        tailored_title = truncate_word_boundary(tailored_title, max_title_chars)

    # 3. Handle AI Disclosure (Must NEVER be cut off)
    body_text = rendition.body
    disclosure_block = ""
    if rendition.is_ai_generated or rendition.ai_disclosure_text:
        disclosure_text = rendition.ai_disclosure_text or "Note: Drafted with assistance from AI, reviewed by human editor."
        disclosure_block = f"\n\n---\n*{disclosure_text}*"

    # 4. Forum Closing Question
    closing_block = ""
    if closing_question and framing == "discussion_first":
        if not body_text.rstrip().endswith("?"):
            closing_block = "\n\nWhat are your thoughts on this? How are you handling this in your environment?"

    # 5. Canonical URL for Articles
    canonical_block = ""
    if attach_canonical and rendition.canonical_url:
        canonical_block = f"\n\n*Originally published at [{rendition.canonical_url}]({rendition.canonical_url})*"

    # Calculate remaining budget for main body so disclosure is NEVER cut off
    reserved_chars = len(disclosure_block) + len(closing_block) + len(canonical_block)
    max_body_content = max_body_chars - reserved_chars

    tailored_body_main = truncate_word_boundary(body_text, max_body_content)
    tailored_body = tailored_body_main + closing_block + canonical_block + disclosure_block

    # 6. Format Tags based on manifest tag_style
    tailored_tags: List[str] = []
    if tag_style == "none" or max_tags == 0:
        tailored_tags = []
    elif tag_style == "hashtag":
        for t in rendition.tags[:max_tags]:
            clean_t = re.sub(r'[^a-zA-Z0-9_]', '', t)
            if clean_t:
                tailored_tags.append(f"#{clean_t}")
    elif tag_style == "slug":
        for t in rendition.tags[:max_tags]:
            clean_slug = re.sub(r'[^a-zA-Z0-9-]', '-', t.lower().strip()).strip('-')
            if clean_slug:
                tailored_tags.append(clean_slug)
    else:
        tailored_tags = rendition.tags[:max_tags]

    tailored_rendition = RenditionSchema(
        title=tailored_title,
        body=tailored_body,
        summary=rendition.summary,
        tags=tailored_tags,
        media_urls=rendition.media_urls,
        canonical_url=rendition.canonical_url,
        is_ai_generated=rendition.is_ai_generated,
        ai_disclosure_text=rendition.ai_disclosure_text,
        metadata={**rendition.metadata, "tailored": True}
    )

    return tailored_rendition, warnings
