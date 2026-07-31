"""Fetch Singapore-based events from community websites and Luma calendars.

Scrapes known SG community pages (SGInnovate, A*STAR, etc.) using requests + BeautifulSoup.
Weekly frequency is well within polite-use norms.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

from src.models import RawItem, load_sources, load_keywords

logger = logging.getLogger(__name__)


def _keyword_match(text: str, keywords: list[str]) -> bool:
    """Check if text contains at least one keyword (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _scrape_html_page(name: str, url: str, keywords: list[str]) -> list[RawItem]:
    """Scrape a community events page for event listings.

    This is best-effort — page structure may change. We look for common patterns:
    links with event-like text, headings near date patterns, etc.
    """
    items: list[RawItem] = []

    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "DigitalBiologyBrief/1.0 (weekly digest bot)"})
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Events SG: failed to fetch '%s': %s", name, exc)
        return []

    soup = BeautifulSoup(resp.text, "lxml")

    # Strategy: look for links that might be events (common patterns in event listing pages)
    # We look for <a> tags within common container patterns
    links = soup.find_all("a", href=True)

    for link in links:
        text = link.get_text(separator=" ", strip=True)
        href = link["href"]

        # Skip navigation, footer, social media links
        if not text or len(text) < 10 or len(text) > 300:
            continue
        if any(skip in href.lower() for skip in ["#", "javascript:", "mailto:", "twitter.com", "facebook.com", "linkedin.com"]):
            continue

        # Keyword filter — is this event-like and relevant?
        if keywords and not _keyword_match(text, keywords):
            continue

        # Build absolute URL
        if href.startswith("/"):
            from urllib.parse import urljoin
            href = urljoin(url, href)
        elif not href.startswith("http"):
            continue

        item_id = f"sg_event:{hashlib.sha256(href.encode()).hexdigest()[:20]}"

        items.append(
            RawItem(
                id=item_id,
                section="events",
                title=text[:200].strip(),
                url=href,
                source_name=name,
                published_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                raw_text=text[:2000],
            )
        )

    return items


def _fetch_luma_calendar(slug: str, keywords: list[str]) -> list[RawItem]:
    """Fetch events from a Luma calendar via its .ics feed or API.

    Luma's public event pages sometimes expose an .ics feed.
    This is best-effort — the exact URL pattern may vary.
    """
    items: list[RawItem] = []
    ics_url = f"https://lu.ma/{slug}/calendar.ics"

    try:
        resp = requests.get(ics_url, timeout=15)
        if resp.status_code != 200:
            logger.warning("Luma: no .ics feed for slug '%s'", slug)
            return []
    except requests.RequestException as exc:
        logger.error("Luma: failed to fetch '%s': %s", slug, exc)
        return []

    # Simple .ics parsing (VEVENT blocks)
    content = resp.text
    events = content.split("BEGIN:VEVENT")

    for event_block in events[1:]:  # skip preamble
        # Extract fields
        summary_match = re.search(r"SUMMARY:(.+)", event_block)
        url_match = re.search(r"URL:(.+)", event_block)
        dtstart_match = re.search(r"DTSTART[^:]*:(\d{8})", event_block)
        description_match = re.search(r"DESCRIPTION:(.+?)(?=\n[A-Z])", event_block, re.DOTALL)
        location_match = re.search(r"LOCATION:(.+)", event_block)

        summary = summary_match.group(1).strip() if summary_match else ""
        url = url_match.group(1).strip() if url_match else f"https://lu.ma/{slug}"
        description = description_match.group(1).strip().replace("\\n", " ") if description_match else ""
        location = location_match.group(1).strip() if location_match else ""

        if not summary:
            continue

        # Date
        pub_date = ""
        if dtstart_match:
            try:
                dt = datetime.strptime(dtstart_match.group(1), "%Y%m%d")
                pub_date = dt.strftime("%Y-%m-%d")
                # Skip past events
                if dt < datetime.now() - timedelta(days=1):
                    continue
            except ValueError:
                pass

        raw_text = f"{summary}. {description} Location: {location}".strip()
        if keywords and not _keyword_match(raw_text, keywords):
            continue

        item_id = f"luma:{hashlib.sha256(url.encode()).hexdigest()[:20]}"

        items.append(
            RawItem(
                id=item_id,
                section="events",
                title=summary[:200],
                url=url,
                source_name="Luma",
                published_at=pub_date,
                raw_text=raw_text[:2000],
            )
        )

    return items


def fetch() -> list[RawItem]:
    """Fetch Singapore events from community pages and Luma calendars.

    Returns a list of RawItem objects with section="events".
    """
    sources_cfg = load_sources()
    config = sources_cfg.get("sg_events", {})
    kw_config = load_keywords()

    event_keywords = kw_config.get("events", {}).get("keywords", [])
    # Also add some generic event-signal words
    event_keywords = event_keywords + ["event", "workshop", "seminar", "conference", "meetup", "talk", "symposium"]

    items: list[RawItem] = []

    # HTML page scraping
    pages = config.get("pages", [])
    for page_info in pages:
        name = page_info.get("name", "SG Events")
        url = page_info.get("url", "")
        if not url:
            continue
        page_items = _scrape_html_page(name, url, event_keywords)
        items.extend(page_items)
        logger.info("Events SG '%s': %d items", name, len(page_items))

    # Luma calendars
    luma_calendars = config.get("luma_calendars", [])
    for slug in luma_calendars:
        luma_items = _fetch_luma_calendar(slug, event_keywords)
        items.extend(luma_items)
        logger.info("Luma '%s': %d items", slug, len(luma_items))

    logger.info("Events SG total: %d items", len(items))
    return items
