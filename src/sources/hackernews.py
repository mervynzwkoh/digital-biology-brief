"""Fetch recent relevant discussions from Hacker News.

Uses the Algolia HN Search API — no authentication required.
Docs: https://hn.algolia.com/api
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

import requests

from src.models import RawItem, load_sources, load_keywords

logger = logging.getLogger(__name__)

HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"


def fetch() -> list[RawItem]:
    """Fetch recent HN stories matching digital biology / ML topics.

    Returns a list of RawItem objects with section="research".
    """
    sources_cfg = load_sources()
    config = sources_cfg.get("hackernews", {})
    min_score = config.get("min_score", 5)
    max_results = config.get("max_results", 30)

    kw_config = load_keywords()
    high_keywords = kw_config.get("research", {}).get("high_weight", [])
    medium_keywords = kw_config.get("research", {}).get("medium_weight", [])

    # Build search queries from high-weight keywords (HN search is best with short queries)
    search_queries = [
        "protein structure prediction",
        "drug discovery AI",
        "AlphaFold",
        "virtual cell",
        "protein design",
        "foundation model biology",
        "diffusion model protein",
    ]

    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=8)).timestamp())

    seen_ids: set[str] = set()
    items: list[RawItem] = []

    for query in search_queries:
        params = {
            "query": query,
            "tags": "story",
            "numericFilters": f"created_at_i>{cutoff_ts},points>{min_score}",
            "hitsPerPage": max_results,
        }

        try:
            resp = requests.get(HN_SEARCH_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.error("HN: query '%s' failed: %s", query, exc)
            continue

        for hit in data.get("hits", []):
            story_id = str(hit.get("objectID", ""))
            if not story_id or story_id in seen_ids:
                continue
            seen_ids.add(story_id)

            title = hit.get("title", "") or ""
            url = hit.get("url", "") or ""
            points = hit.get("points", 0) or 0
            num_comments = hit.get("num_comments", 0) or 0
            created_at = hit.get("created_at", "") or ""

            # If no external URL, link to the HN discussion
            if not url:
                url = f"https://news.ycombinator.com/item?id={story_id}"

            hn_discussion_url = f"https://news.ycombinator.com/item?id={story_id}"

            # Parse date
            pub_date = ""
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    pub_date = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

            raw_text = f"{title}. HN discussion: {hn_discussion_url} ({points} points, {num_comments} comments)"

            items.append(
                RawItem(
                    id=f"hn:{story_id}",
                    section="research",
                    title=title.strip(),
                    url=url,
                    source_name="Hacker News",
                    published_at=pub_date,
                    raw_text=raw_text[:2000],
                )
            )

    logger.info("Hacker News: fetched %d items", len(items))
    return items
