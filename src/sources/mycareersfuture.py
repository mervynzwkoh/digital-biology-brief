"""Fetch job listings from MyCareersFuture (Singapore government job portal).

Public API — no authentication or API key required.
Salary disclosure is legally mandated so listings include pay ranges.
"""

from __future__ import annotations

import hashlib
import logging

import requests

from src.models import RawItem, load_keywords

logger = logging.getLogger(__name__)

MCF_API_URL = "https://api.mycareersfuture.gov.sg/v2/jobs"


def fetch() -> list[RawItem]:
    """Fetch relevant job listings from MyCareersFuture.

    Returns a list of RawItem objects with section="jobs".
    """
    kw_config = load_keywords()
    job_keywords = kw_config.get("jobs", {}).get("keywords", [])

    search_queries = [
        "computational biology",
        "bioinformatics",
        "machine learning",
        "drug discovery",
        "data science biology",
        "AI research",
    ]

    seen_ids: set[str] = set()
    items: list[RawItem] = []

    for query in search_queries:
        params = {
            "search": query,
            "limit": 20,
            "page": 0,
            "sortBy": "new_posting_date",
        }

        try:
            resp = requests.get(
                MCF_API_URL,
                params=params,
                timeout=20,
                headers={
                    "User-Agent": "DigitalBiologyBrief/1.0",
                    "Accept": "application/json",
                },
            )
            if resp.status_code != 200:
                logger.warning("MyCareersFuture: status %d for query '%s'", resp.status_code, query)
                continue
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.error("MyCareersFuture: query '%s' failed: %s", query, exc)
            continue

        results = data.get("results", [])

        for job in results:
            job_id = job.get("uuid", "") or ""
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            title = job.get("title", "") or ""
            company = ""
            company_info = job.get("postedCompany", {})
            if isinstance(company_info, dict):
                company = company_info.get("name", "") or ""

            # Salary range — structure varies; handle robustly
            salary_str = ""
            try:
                salary_data = job.get("salary", {})
                if isinstance(salary_data, dict):
                    salary_min = salary_data.get("minimum", "")
                    salary_max = salary_data.get("maximum", "")
                    # Values may be ints or nested dicts with 'amount'
                    if isinstance(salary_min, dict):
                        salary_min = salary_min.get("amount", "")
                    if isinstance(salary_max, dict):
                        salary_max = salary_max.get("amount", "")
                    if salary_min and salary_max:
                        salary_str = f"SGD {salary_min} - {salary_max}"
                    elif salary_min:
                        salary_str = f"SGD {salary_min}+"
            except Exception:
                salary_str = ""

            # Description
            description = job.get("description", "") or ""
            # Strip HTML tags
            import re
            description = re.sub(r"<[^>]+>", " ", description)
            description = re.sub(r"\s+", " ", description).strip()

            # Posted date
            posted_date = job.get("metadata", {}).get("newPostingDate", "") or ""
            if posted_date and "T" in posted_date:
                posted_date = posted_date.split("T")[0]

            # Build URL
            # MCF job URLs use the UUID
            url = f"https://www.mycareersfuture.gov.sg/job/{job_id}"

            raw_text = f"Company: {company}. {salary_str}. {description}"

            if not title:
                continue

            items.append(
                RawItem(
                    id=f"mcf:{job_id}",
                    section="jobs",
                    title=title.strip(),
                    url=url,
                    source_name="MyCareersFuture",
                    published_at=posted_date,
                    raw_text=raw_text[:2000].strip(),
                )
            )

    logger.info("MyCareersFuture: fetched %d items", len(items))
    return items
