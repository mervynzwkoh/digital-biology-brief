"""Fetch recent papers from arXiv matching digital biology / ML topics.

Uses the arXiv API (Atom feed) — no authentication required.
Docs: https://info.arxiv.org/help/api/
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

from src.models import RawItem, load_sources

logger = logging.getLogger(__name__)

ARXIV_API_URL = "https://export.arxiv.org/api/query"
NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}


def _build_query(config: dict) -> str:
    """Build an arXiv search query string from config categories + keyword filter.

    Strategy: q-bio.* papers are inherently relevant, so they only get a light
    keyword filter.  cs.LG / cs.AI papers MUST match biology-specific terms to
    avoid pulling in pure ML work.
    """
    categories = config.get("categories", ["q-bio.BM", "cs.LG", "cs.AI"])
    keyword_filter = config.get("keyword_filter", [])

    # Split categories into biology-native vs ML-general
    bio_cats = [c for c in categories if c.startswith("q-bio")]
    ml_cats = [c for c in categories if not c.startswith("q-bio")]

    # Biology-specific keywords that cs.LG/cs.AI papers must match
    bio_keywords = [
        kw for kw in keyword_filter
        if kw.lower() not in ("diffusion", "foundation model", "transformer")
    ]

    clauses = []

    # q-bio papers: include if they match any keyword (broad — these are already bio)
    if bio_cats:
        bio_cat_clause = " OR ".join(f"cat:{c}" for c in bio_cats)
        if keyword_filter:
            kw_parts = []
            for kw in keyword_filter:
                kw_parts.append(f'ti:"{kw}"')
                kw_parts.append(f'abs:"{kw}"')
            clauses.append(f"(({bio_cat_clause}) AND ({' OR '.join(kw_parts)}))")
        else:
            clauses.append(f"({bio_cat_clause})")

    # cs.LG/cs.AI papers: only include with strict biology-specific keywords
    if ml_cats and bio_keywords:
        ml_cat_clause = " OR ".join(f"cat:{c}" for c in ml_cats)
        kw_parts = []
        for kw in bio_keywords:
            kw_parts.append(f'ti:"{kw}"')
            kw_parts.append(f'abs:"{kw}"')
        clauses.append(f"(({ml_cat_clause}) AND ({' OR '.join(kw_parts)}))")

    return " OR ".join(clauses) if clauses else "cat:q-bio.BM"


def fetch() -> list[RawItem]:
    """Fetch recent arXiv papers matching configured categories and keywords.

    Returns a list of RawItem objects with section="research".
    """
    sources_cfg = load_sources()
    config = sources_cfg.get("arxiv", {})
    max_results = config.get("max_results", 100)

    query = _build_query(config)
    cutoff = datetime.now(timezone.utc) - timedelta(days=8)  # slight buffer over 7 days

    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    logger.info("arXiv: querying with %d max results", max_results)

    try:
        resp = requests.get(ARXIV_API_URL, params=params, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("arXiv: request failed: %s", exc)
        return []

    root = ET.fromstring(resp.text)
    items: list[RawItem] = []

    for entry in root.findall("atom:entry", NAMESPACE):
        # Parse published date
        published_el = entry.find("atom:published", NAMESPACE)
        if published_el is None or published_el.text is None:
            continue
        published_str = published_el.text.strip()
        try:
            published_dt = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        except ValueError:
            continue

        if published_dt < cutoff:
            continue

        # Extract fields
        title_el = entry.find("atom:title", NAMESPACE)
        title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""

        summary_el = entry.find("atom:summary", NAMESPACE)
        abstract = (summary_el.text or "").strip().replace("\n", " ") if summary_el is not None else ""

        # arXiv ID from the <id> element (e.g. http://arxiv.org/abs/2301.12345v1)
        id_el = entry.find("atom:id", NAMESPACE)
        arxiv_url = (id_el.text or "").strip() if id_el is not None else ""
        arxiv_id = arxiv_url.split("/abs/")[-1] if "/abs/" in arxiv_url else arxiv_url

        # Prefer the abstract page link
        link_url = arxiv_url
        for link_el in entry.findall("atom:link", NAMESPACE):
            if link_el.get("type") == "text/html":
                link_url = link_el.get("href", arxiv_url)
                break

        if not title or not arxiv_id:
            continue

        items.append(
            RawItem(
                id=f"arxiv:{arxiv_id}",
                section="research",
                title=title,
                url=link_url,
                source_name="arXiv",
                published_at=published_dt.strftime("%Y-%m-%d"),
                raw_text=abstract[:2000],
            )
        )

    logger.info("arXiv: fetched %d items", len(items))
    return items
