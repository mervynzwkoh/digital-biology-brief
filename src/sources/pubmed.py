"""Fetch recent papers from PubMed via NCBI E-utilities.

Uses esearch + efetch pipeline — no authentication required.
An email and tool name are sent per NCBI etiquette.
Docs: https://www.ncbi.nlm.nih.gov/books/NBK25500/
"""

from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

from src.models import RawItem, load_sources

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def fetch() -> list[RawItem]:
    """Fetch recent PubMed papers matching configured search terms.

    Returns a list of RawItem objects with section="research".
    """
    sources_cfg = load_sources()
    config = sources_cfg.get("pubmed", {})
    search_terms = config.get("search_terms", [])
    max_results = config.get("max_results", 50)
    email = os.environ.get("NCBI_EMAIL", config.get("email", ""))
    tool_name = config.get("tool_name", "digital-biology-brief")

    now = datetime.now(timezone.utc)
    date_from = (now - timedelta(days=8)).strftime("%Y/%m/%d")
    date_to = now.strftime("%Y/%m/%d")

    all_pmids: list[str] = []

    # Step 1: esearch — collect PMIDs across all search terms
    for term in search_terms:
        params = {
            "db": "pubmed",
            "term": term,
            "retmax": max_results,
            "datetype": "pdat",
            "mindate": date_from,
            "maxdate": date_to,
            "retmode": "json",
            "tool": tool_name,
            "email": email,
        }
        try:
            resp = requests.get(ESEARCH_URL, params=params, timeout=20)
            resp.raise_for_status()
            result = resp.json()
            ids = result.get("esearchresult", {}).get("idlist", [])
            all_pmids.extend(ids)
        except (requests.RequestException, ValueError) as exc:
            logger.error("PubMed esearch failed for '%s': %s", term, exc)

    # Deduplicate PMIDs
    all_pmids = list(dict.fromkeys(all_pmids))

    if not all_pmids:
        logger.info("PubMed: no results found")
        return []

    logger.info("PubMed: fetching details for %d PMIDs", len(all_pmids))

    # Step 2: efetch — get details in XML
    items: list[RawItem] = []
    batch_size = 50

    for i in range(0, len(all_pmids), batch_size):
        batch = all_pmids[i : i + batch_size]
        params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "rettype": "xml",
            "retmode": "xml",
            "tool": tool_name,
            "email": email,
        }
        try:
            resp = requests.get(EFETCH_URL, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("PubMed efetch failed: %s", exc)
            continue

        root = ET.fromstring(resp.text)

        for article in root.findall(".//PubmedArticle"):
            try:
                medline = article.find("MedlineCitation")
                if medline is None:
                    continue

                pmid_el = medline.find("PMID")
                pmid = pmid_el.text if pmid_el is not None else ""

                article_el = medline.find("Article")
                if article_el is None:
                    continue

                # Title
                title_el = article_el.find("ArticleTitle")
                title = (title_el.text or "") if title_el is not None else ""

                # Abstract
                abstract_parts = []
                abstract_el = article_el.find("Abstract")
                if abstract_el is not None:
                    for abs_text in abstract_el.findall("AbstractText"):
                        label = abs_text.get("Label", "")
                        text = "".join(abs_text.itertext()).strip()
                        if label:
                            abstract_parts.append(f"{label}: {text}")
                        else:
                            abstract_parts.append(text)
                abstract = " ".join(abstract_parts)

                # Publication date
                pub_date_el = article_el.find(".//PubDate")
                pub_date = ""
                if pub_date_el is not None:
                    year = (pub_date_el.find("Year").text or "") if pub_date_el.find("Year") is not None else ""
                    month = (pub_date_el.find("Month").text or "") if pub_date_el.find("Month") is not None else "01"
                    day = (pub_date_el.find("Day").text or "") if pub_date_el.find("Day") is not None else "01"
                    # Month might be text like "Jan"
                    try:
                        month_num = datetime.strptime(month, "%b").month if not month.isdigit() else int(month)
                    except ValueError:
                        month_num = 1
                    if year:
                        pub_date = f"{year}-{month_num:02d}-{int(day):02d}"

                if not title or not pmid:
                    continue

                items.append(
                    RawItem(
                        id=f"pubmed:{pmid}",
                        section="research",
                        title=title.strip(),
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        source_name="PubMed",
                        published_at=pub_date,
                        raw_text=abstract[:2000].strip(),
                    )
                )
            except Exception as exc:
                logger.warning("PubMed: failed to parse article: %s", exc)
                continue

    logger.info("PubMed: fetched %d items", len(items))
    return items
