"""Fetch job listings from Greenhouse and Lever ATS boards.

Both expose free, public, unauthenticated JSON APIs per-company.
- Greenhouse: boards-api.greenhouse.io/v1/boards/{company}/jobs
- Lever: api.lever.co/v0/postings/{company}
"""

from __future__ import annotations

import hashlib
import logging
import re

import requests

from src.models import RawItem, load_companies, load_keywords

logger = logging.getLogger(__name__)

GREENHOUSE_API_URL = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
LEVER_API_URL = "https://api.lever.co/v0/postings/{company}"


def _keyword_match(text: str, keywords: list[str]) -> bool:
    """Check if text contains at least one keyword (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _is_sg_or_remote(location: str) -> bool:
    """Check if a job location is Singapore or remote."""
    loc_lower = location.lower()
    return any(
        term in loc_lower
        for term in ["singapore", "sg", "remote", "anywhere", "global", "apac", "asia"]
    )


def _fetch_greenhouse(company: str, keywords: list[str]) -> list[RawItem]:
    """Fetch jobs from a single Greenhouse board."""
    url = GREENHOUSE_API_URL.format(company=company)
    items: list[RawItem] = []

    try:
        resp = requests.get(url, params={"content": "true"}, timeout=15)
        if resp.status_code == 404:
            logger.warning("Greenhouse: company '%s' not found", company)
            return []
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error("Greenhouse '%s': %s", company, exc)
        return []

    for job in data.get("jobs", []):
        title = job.get("title", "") or ""
        job_id = str(job.get("id", ""))
        location = ""
        location_info = job.get("location", {})
        if isinstance(location_info, dict):
            location = location_info.get("name", "") or ""

        # Filter for SG/remote
        if not _is_sg_or_remote(location) and not _is_sg_or_remote(title):
            continue

        # Keyword relevance
        content = job.get("content", "") or ""
        clean_content = re.sub(r"<[^>]+>", " ", content)
        clean_content = re.sub(r"\s+", " ", clean_content).strip()

        combined_text = f"{title} {clean_content}"
        if keywords and not _keyword_match(combined_text, keywords):
            continue

        absolute_url = job.get("absolute_url", "") or ""
        updated_at = job.get("updated_at", "") or ""
        if updated_at and "T" in updated_at:
            updated_at = updated_at.split("T")[0]

        raw_text = f"Company: {company}. Location: {location}. {clean_content}"

        items.append(
            RawItem(
                id=f"gh:{company}:{job_id}",
                section="jobs",
                title=title.strip(),
                url=absolute_url,
                source_name=f"Greenhouse ({company})",
                published_at=updated_at,
                raw_text=raw_text[:2000].strip(),
            )
        )

    return items


def _fetch_lever(company: str, keywords: list[str]) -> list[RawItem]:
    """Fetch jobs from a single Lever board."""
    url = LEVER_API_URL.format(company=company)
    items: list[RawItem] = []

    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 404:
            logger.warning("Lever: company '%s' not found", company)
            return []
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error("Lever '%s': %s", company, exc)
        return []

    if not isinstance(data, list):
        return []

    for posting in data:
        title = posting.get("text", "") or ""
        posting_id = posting.get("id", "") or ""
        location = ""
        categories = posting.get("categories", {})
        if isinstance(categories, dict):
            location = categories.get("location", "") or ""

        # Filter for SG/remote
        if not _is_sg_or_remote(location) and not _is_sg_or_remote(title):
            continue

        description_plain = posting.get("descriptionPlain", "") or ""
        additional_plain = posting.get("additionalPlain", "") or ""
        full_text = f"{description_plain} {additional_plain}".strip()

        combined_text = f"{title} {full_text}"
        if keywords and not _keyword_match(combined_text, keywords):
            continue

        apply_url = posting.get("hostedUrl", "") or posting.get("applyUrl", "") or ""
        created_at = posting.get("createdAt", 0)

        # Lever uses millisecond timestamps
        pub_date = ""
        if created_at:
            try:
                from datetime import datetime, timezone
                dt = datetime.fromtimestamp(created_at / 1000, tz=timezone.utc)
                pub_date = dt.strftime("%Y-%m-%d")
            except (ValueError, OSError):
                pass

        raw_text = f"Company: {company}. Location: {location}. {full_text}"

        items.append(
            RawItem(
                id=f"lever:{company}:{posting_id}",
                section="jobs",
                title=title.strip(),
                url=apply_url,
                source_name=f"Lever ({company})",
                published_at=pub_date,
                raw_text=raw_text[:2000].strip(),
            )
        )

    return items


def fetch() -> list[RawItem]:
    """Fetch job listings from all configured Greenhouse and Lever boards.

    Returns a list of RawItem objects with section="jobs".
    """
    companies_cfg = load_companies()
    kw_config = load_keywords()
    job_keywords = kw_config.get("jobs", {}).get("keywords", [])

    items: list[RawItem] = []

    # Greenhouse companies
    gh_companies = companies_cfg.get("greenhouse", [])
    for company in gh_companies:
        company_items = _fetch_greenhouse(company, job_keywords)
        items.extend(company_items)
        logger.info("Greenhouse '%s': %d items", company, len(company_items))

    # Lever companies
    lever_companies = companies_cfg.get("lever", [])
    for company in lever_companies:
        company_items = _fetch_lever(company, job_keywords)
        items.extend(company_items)
        logger.info("Lever '%s': %d items", company, len(company_items))

    logger.info("ATS boards total: %d items", len(items))
    return items
