"""Audience Relevance Scoring Algorithm (Advanced Level 3).

Computes relevance score (1.0 to 5.0) against IncuBrix target audiences:
- AI (artificial intelligence, machine learning, generative ai, llm)
- Video (video production, editing, creators, youtube, media)
- Marketing (growth, seo, syndication, audience building)
- SaaS (software-as-a-service, cloud, b2b, developers)
- Creators (creator economy, content publishing, writers)
- Founders (startups, entrepreneurship, indie hackers, bootstrapping)

CRITICAL REQUIREMENT:
A destination with NO audience signal must NOT score above 2.0.
"""

from typing import List, Dict, Any, Tuple

AUDIENCE_PILLARS = {
    "ai": {"ai", "artificial intelligence", "machine learning", "ml", "llm", "generative ai", "neural", "deep learning", "gpt"},
    "video": {"video", "video editing", "video production", "youtube", "media", "motion graphics", "streaming", "shorts", "reels"},
    "marketing": {"marketing", "growth", "seo", "distribution", "social media", "syndication", "copywriting", "funnels"},
    "saas": {"saas", "b2b", "software", "cloud", "dev", "developer", "engineering", "api", "fastapi", "python"},
    "creators": {"creator", "creators", "creator economy", "blogging", "newsletter", "podcasting", "writers", "publishers"},
    "founders": {"founder", "founders", "startup", "startups", "entrepreneurship", "indie hacker", "bootstrapping", "venture"}
}


def compute_audience_relevance(
    name: str = "",
    category: str = "",
    tags: List[str] = None,
    description: str = ""
) -> Tuple[float, str]:
    """
    Computes a 1.0 to 5.0 score and a concise explanation based on keyword and semantic signals.
    Enforces that destinations with no audience signals never score above 2.0.
    """
    tags = tags or []
    all_text = f"{name} {category} {' '.join(tags)} {description}".lower()

    # Find matched pillars
    matched_pillars: Dict[str, List[str]] = {}
    for pillar, keywords in AUDIENCE_PILLARS.items():
        hits = [kw for kw in keywords if kw in all_text]
        if hits:
            matched_pillars[pillar] = hits

    num_pillars = len(matched_pillars)

    # Hard rule: A destination with no audience signal must not score above 2.0
    if num_pillars == 0:
        return 1.5, "No audience signal matching IncuBrix target verticals (AI, video, marketing, SaaS, creators, founders). Score strictly capped at <= 2.0."

    # Compute score based on pillar coverage and keyword depth
    total_hits = sum(len(hits) for hits in matched_pillars.values())

    if num_pillars == 1:
        score = 2.5 if total_hits == 1 else 3.0
    elif num_pillars == 2:
        score = 3.5 if total_hits < 4 else 4.0
    elif num_pillars == 3:
        score = 4.2 if total_hits < 6 else 4.6
    else:  # 4 or more pillars
        score = 4.8 if total_hits < 8 else 5.0

    score = min(5.0, max(1.0, round(score, 1)))

    matched_names = ", ".join(f"{p.upper()} ({len(h)})" for p, h in sorted(matched_pillars.items()))
    explanation = f"Matches {num_pillars} target IncuBrix audience pillar(s): {matched_names} with {total_hits} signal keyword(s)."

    return score, explanation
