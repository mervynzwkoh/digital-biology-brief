"""Fetch recent papers from Semantic Scholar.

Uses the public API (optional API key for higher rate limits).
Docs: https://api.semanticscholar.org/
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import requests

from src.models import RawItem, load_sources

logger = logging.getLogger(__name__)

S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


def fetch() -> list[RawItem]:
    """Fetch recent Semantic Scholar papers matching configured search queries.

    Returns a list of RawItem objects with section="research".
    """
    sources_cfg = load_sources()
    config = sources_cfg.get("semantic_scholar", {})
    queries = config.get("search_queries", [])
    fields = config.get("fields", "title,url,abstract,publicationDate,citationCount,externalIds")
    max_results = config.get("max_results", 50)

    api_key = os.environ.get("S2_API_KEY", "")
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    cutoff = datetime.now(timezone.utc) - timedelta(days=8)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    seen_ids: set[str] = set()
    items: list[RawItem] = []

    for query in queries:
        params = {
            "query": query,
            "limit": min(max_results, 100),  # S2 max per request is 100
            "fields": fields,
            "publicationDateOrYear": f"{cutoff_str}:",
        }

        try:
            resp = requests.get(S2_SEARCH_URL, params=params, headers=headers, timeout=20)
            if resp.status_code == 429:
                logger.warning("Semantic Scholar: rate limited on query '%s'", query)
                continue
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.error("Semantic Scholar: query '%s' failed: %s", query, exc)
            continue

        for paper in data.get("data", []):
            paper_id = paper.get("paperId", "")
            if not paper_id or paper_id in seen_ids:
                continue
            seen_ids.add(paper_id)

            title = paper.get("title", "") or ""
            abstract = paper.get("abstract", "") or ""
            url = paper.get("url", "") or ""
            pub_date = paper.get("publicationDate", "") or ""

            # Build a more specific ID if possible (DOI or arXiv ID)
            external_ids = paper.get("externalIds") or {}
            doi = external_ids.get("DOI", "")
            arxiv_id = external_ids.get("ArXiv", "")
            stable_id = f"doi:{doi}" if doi else (f"arxiv:{arxiv_id}" if arxiv_id else f"s2:{paper_id}")

            if not title:
                continue

            # Include citation count in raw_text for ranking signal
            citation_count = paper.get("citationCount", 0) or 0
            raw_text = abstract
            if citation_count > 0:
                raw_text = f"[Citations: {citation_count}] {abstract}"

            items.append(
                RawItem(
                    id=stable_id,
                    section="research",
                    title=title.strip(),
                    url=url,
                    source_name="Semantic Scholar",
                    published_at=pub_date,
                    raw_text=raw_text[:2000].strip(),
                )
            )

    logger.info("Semantic Scholar: fetched %d items", len(items))
    return items
