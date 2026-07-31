"""Fetch recent preprints from bioRxiv and medRxiv.

Uses the public bioRxiv API — no authentication required.
Docs: https://api.biorxiv.org/
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests

from src.models import RawItem, load_sources, load_keywords

logger = logging.getLogger(__name__)

BIORXIV_API_BASE = "https://api.biorxiv.org/details"


def _keyword_match(text: str, keywords: list[str]) -> bool:
    """Check if text contains at least one keyword (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _fetch_server(server: str, date_from: str, date_to: str, config: dict) -> list[RawItem]:
    """Fetch from one server (biorxiv or medrxiv)."""
    max_results = config.get("max_results", 100)
    allowed_categories = {c.lower() for c in config.get("categories", [])}

    # Get keyword list for relevance filtering
    kw_config = load_keywords()
    all_keywords = (
        kw_config.get("research", {}).get("high_weight", [])
        + kw_config.get("research", {}).get("medium_weight", [])
    )

    url = f"{BIORXIV_API_BASE}/{server}/{date_from}/{date_to}/0/{max_results}"
    logger.info("%s: fetching %s", server, url)

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error("%s: request failed: %s", server, exc)
        return []

    collection = data.get("collection", [])
    items: list[RawItem] = []

    for entry in collection:
        category = (entry.get("category", "") or "").lower()
        title = entry.get("title", "") or ""
        abstract = entry.get("abstract", "") or ""

        # Category filter
        if allowed_categories and category not in allowed_categories:
            continue

        # Keyword relevance filter
        combined_text = f"{title} {abstract}"
        if all_keywords and not _keyword_match(combined_text, all_keywords):
            continue

        doi = entry.get("doi", "")
        pub_date = entry.get("date", "")
        item_id = f"{server}:{doi}" if doi else f"{server}:{hash(title)}"

        items.append(
            RawItem(
                id=item_id,
                section="research",
                title=title.strip(),
                url=f"https://doi.org/{doi}" if doi else "",
                source_name=server.capitalize(),
                published_at=pub_date,
                raw_text=abstract[:2000].strip(),
            )
        )

    return items


def fetch() -> list[RawItem]:
    """Fetch recent preprints from bioRxiv and medRxiv.

    Returns a list of RawItem objects with section="research".
    """
    sources_cfg = load_sources()
    config = sources_cfg.get("biorxiv", {})

    now = datetime.now(timezone.utc)
    date_to = now.strftime("%Y-%m-%d")
    date_from = (now - timedelta(days=8)).strftime("%Y-%m-%d")

    items: list[RawItem] = []

    for server in ("biorxiv", "medrxiv"):
        server_items = _fetch_server(server, date_from, date_to, config)
        items.extend(server_items)
        logger.info("%s: fetched %d items", server, len(server_items))

    logger.info("bioRxiv/medRxiv total: %d items", len(items))
    return items
