"""Fetch recent posts from lab/company blogs and journal TOC RSS feeds.

Uses feedparser to parse RSS/Atom feeds — no authentication required.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser

from src.models import RawItem, load_sources, load_keywords

logger = logging.getLogger(__name__)


def _keyword_match(text: str, keywords: list[str]) -> bool:
    """Check if text contains at least one keyword (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _parse_feed_date(entry: dict) -> datetime | None:
    """Try to extract a datetime from a feedparser entry."""
    for date_field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(date_field)
        if parsed:
            try:
                return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
            except (ValueError, OverflowError, OSError):
                continue
    return None


def _process_feed(
    feed_name: str,
    feed_url: str,
    cutoff: datetime,
    keywords: list[str],
    require_keyword: bool = True,
) -> list[RawItem]:
    """Parse a single RSS feed and return matching RawItems."""
    items: list[RawItem] = []

    try:
        parsed = feedparser.parse(feed_url)
    except Exception as exc:
        logger.error("RSS: failed to parse '%s' (%s): %s", feed_name, feed_url, exc)
        return []

    if parsed.bozo and not parsed.entries:
        logger.warning("RSS: feed '%s' is malformed and has no entries", feed_name)
        return []

    for entry in parsed.entries:
        pub_dt = _parse_feed_date(entry)
        if pub_dt is not None and pub_dt < cutoff:
            continue

        title = entry.get("title", "") or ""
        link = entry.get("link", "") or ""
        summary = entry.get("summary", "") or ""
        content_parts = entry.get("content", [])
        if content_parts and isinstance(content_parts, list):
            full_text = content_parts[0].get("value", summary)
        else:
            full_text = summary

        # Clean HTML tags from summary (basic)
        import re
        clean_text = re.sub(r"<[^>]+>", " ", full_text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        combined = f"{title} {clean_text}"
        if require_keyword and keywords and not _keyword_match(combined, keywords):
            continue

        # Generate stable ID from URL or title hash
        item_id = link if link else hashlib.sha256(title.encode()).hexdigest()[:16]
        stable_id = f"rss:{hashlib.sha256(item_id.encode()).hexdigest()[:20]}"

        pub_date_str = pub_dt.strftime("%Y-%m-%d") if pub_dt else ""

        items.append(
            RawItem(
                id=stable_id,
                section="research",
                title=title.strip(),
                url=link,
                source_name=feed_name,
                published_at=pub_date_str,
                raw_text=clean_text[:2000],
            )
        )

    return items


def fetch() -> list[RawItem]:
    """Fetch recent entries from all configured RSS feeds.

    Returns a list of RawItem objects with section="research".
    """
    sources_cfg = load_sources()
    kw_config = load_keywords()

    all_keywords = (
        kw_config.get("research", {}).get("high_weight", [])
        + kw_config.get("research", {}).get("medium_weight", [])
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=8)

    items: list[RawItem] = []

    # Lab/company blogs
    blog_feeds = sources_cfg.get("rss_blogs", {}).get("feeds", [])
    for feed_info in blog_feeds:
        name = feed_info.get("name", "Unknown Blog")
        url = feed_info.get("url", "")
        if not url:
            continue
        feed_items = _process_feed(name, url, cutoff, all_keywords, require_keyword=True)
        items.extend(feed_items)
        logger.info("RSS blog '%s': %d items", name, len(feed_items))

    # Journal TOC feeds — these are generally more relevant, lighter keyword filter
    journal_feeds = sources_cfg.get("rss_journals", {}).get("feeds", [])
    for feed_info in journal_feeds:
        name = feed_info.get("name", "Unknown Journal")
        url = feed_info.get("url", "")
        if not url:
            continue
        feed_items = _process_feed(name, url, cutoff, all_keywords, require_keyword=True)
        items.extend(feed_items)
        logger.info("RSS journal '%s': %d items", name, len(feed_items))

    logger.info("RSS total: %d items", len(items))
    return items
