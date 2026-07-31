"""Pre-LLM relevance scoring and ranking of ingested items.

Uses keyword weights from config/keywords.yaml to score items.
High-weight keywords = 3 points, medium-weight = 1 point.
Items are sorted by score descending and capped per section.
"""

from __future__ import annotations

import logging

from src.models import RawItem, load_keywords, load_sources

logger = logging.getLogger(__name__)


def _score_item(item: RawItem, high_keywords: list[str], medium_keywords: list[str]) -> float:
    """Compute a relevance score for a single item based on keyword matches."""
    text = f"{item.title} {item.raw_text}".lower()
    score = 0.0

    for kw in high_keywords:
        if kw.lower() in text:
            score += 3.0

    for kw in medium_keywords:
        if kw.lower() in text:
            score += 1.0

    return score


def rank_and_cap(items: list[RawItem]) -> list[RawItem]:
    """Score, sort, and cap items per section.

    Args:
        items: De-duplicated items from all sources.

    Returns:
        Ranked and capped items, grouped by section.
    """
    kw_config = load_keywords()
    sources_cfg = load_sources()
    caps = sources_cfg.get("item_caps", {})

    # Section-specific keyword lists
    research_high = kw_config.get("research", {}).get("high_weight", [])
    research_medium = kw_config.get("research", {}).get("medium_weight", [])
    events_keywords = kw_config.get("events", {}).get("keywords", [])
    jobs_keywords = kw_config.get("jobs", {}).get("keywords", [])

    # Section caps
    research_cap = caps.get("research", 12)
    events_cap = caps.get("events", 8)
    jobs_cap = caps.get("jobs", 15)

    # Group by section
    research_items = [i for i in items if i.section == "research"]
    events_items = [i for i in items if i.section == "events"]
    jobs_items = [i for i in items if i.section == "jobs"]

    # Score and sort research
    scored_research = [
        (item, _score_item(item, research_high, research_medium))
        for item in research_items
    ]
    scored_research.sort(key=lambda x: x[1], reverse=True)

    # Score events (all event keywords at weight 1)
    scored_events = [
        (item, _score_item(item, events_keywords, []))
        for item in events_items
    ]
    scored_events.sort(key=lambda x: x[1], reverse=True)

    # Score jobs (all job keywords at weight 1)
    scored_jobs = [
        (item, _score_item(item, jobs_keywords, []))
        for item in jobs_items
    ]
    scored_jobs.sort(key=lambda x: x[1], reverse=True)

    # Cap and collect
    result: list[RawItem] = []

    for item, score in scored_research[:research_cap]:
        result.append(item)
    logger.info(
        "Rank: research %d → %d (cap=%d)",
        len(research_items),
        min(len(scored_research), research_cap),
        research_cap,
    )

    for item, score in scored_events[:events_cap]:
        result.append(item)
    logger.info(
        "Rank: events %d → %d (cap=%d)",
        len(events_items),
        min(len(scored_events), events_cap),
        events_cap,
    )

    for item, score in scored_jobs[:jobs_cap]:
        result.append(item)
    logger.info(
        "Rank: jobs %d → %d (cap=%d)",
        len(jobs_items),
        min(len(scored_jobs), jobs_cap),
        jobs_cap,
    )

    logger.info("Rank: total output = %d items", len(result))
    return result
