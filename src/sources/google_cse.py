"""Fetch results from Google Custom Search Engine (Programmable Search).

Used for two purposes:
1. LinkedIn public posts/pulse as a research social-chatter proxy (ToS-compliant)
2. Events on Eventbrite/Luma

Requires GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX environment variables.
Free tier: 100 queries/day.
Docs: https://developers.google.com/custom-search/v1/overview
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone

import requests

from src.models import RawItem, load_sources

logger = logging.getLogger(__name__)

GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"


def _search(
    query: str,
    api_key: str,
    cx: str,
    max_results: int = 10,
    date_restrict: str = "w1",  # last 1 week
) -> list[dict]:
    """Run a single Google CSE query and return result items."""
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": min(max_results, 10),  # CSE max per request is 10
        "dateRestrict": date_restrict,
    }

    try:
        resp = requests.get(GOOGLE_CSE_URL, params=params, timeout=15)
        if resp.status_code == 403:
            logger.warning("Google CSE: quota exceeded or invalid key")
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("items", [])
    except (requests.RequestException, ValueError) as exc:
        logger.error("Google CSE: query '%s' failed: %s", query, exc)
        return []


def _results_to_items(results: list[dict], section: str, source_label: str) -> list[RawItem]:
    """Convert Google CSE results to RawItems."""
    items: list[RawItem] = []

    for result in results:
        title = result.get("title", "") or ""
        link = result.get("link", "") or ""
        snippet = result.get("snippet", "") or ""

        if not title or not link:
            continue

        item_id = f"gcse:{hashlib.sha256(link.encode()).hexdigest()[:20]}"

        items.append(
            RawItem(
                id=item_id,
                section=section,
                title=title.strip(),
                url=link,
                source_name=source_label,
                published_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                raw_text=snippet[:2000].strip(),
            )
        )

    return items


def fetch() -> list[RawItem]:
    """Fetch results from Google CSE for LinkedIn proxy and events.

    Returns a list of RawItem objects with section="research" or "events".
    """
    api_key = os.environ.get("GOOGLE_CSE_API_KEY", "")
    cx = os.environ.get("GOOGLE_CSE_CX", "")

    if not api_key or not cx:
        logger.warning("Google CSE: GOOGLE_CSE_API_KEY or GOOGLE_CSE_CX not set, skipping")
        return []

    sources_cfg = load_sources()
    config = sources_cfg.get("google_cse", {})

    items: list[RawItem] = []

    # 1. LinkedIn public posts as research signal
    linkedin_queries = config.get("linkedin_queries", [])
    site_restrict = config.get("linkedin_site_restrict", "")
    max_per_query = config.get("max_results_per_query", 10)

    for query in linkedin_queries:
        full_query = f"{query} {site_restrict}" if site_restrict else query
        results = _search(full_query, api_key, cx, max_per_query)
        linkedin_items = _results_to_items(results, "research", "LinkedIn (via Google)")
        items.extend(linkedin_items)
        logger.info("Google CSE LinkedIn: '%s' → %d items", query, len(linkedin_items))

    # 2. Events (Eventbrite, Luma)
    events_queries = config.get("events_queries", [])
    events_site_restrict = config.get("events_site_restrict", "")

    for query in events_queries:
        full_query = f"{query} {events_site_restrict}" if events_site_restrict else query
        results = _search(full_query, api_key, cx, max_per_query)
        event_items = _results_to_items(results, "events", "Google CSE Events")
        items.extend(event_items)
        logger.info("Google CSE Events: '%s' → %d items", query, len(event_items))

    logger.info("Google CSE total: %d items", len(items))
    return items
