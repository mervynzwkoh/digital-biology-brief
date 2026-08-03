"""LLM summarization of ranked items using Anthropic Claude Haiku 4.5.

Batches 5-8 items per API call to reduce cost and call overhead.
Research items get a deep 5-section analysis; events/jobs get lightweight extraction.
"""

from __future__ import annotations

import logging
import os
import re

import anthropic

from src.models import RawItem, SummarizedItem

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20241022"
RESEARCH_BATCH_SIZE = 5
EVENTS_JOBS_BATCH_SIZE = 8


# ── Prompt templates ───────────────────────────────────────────────────────────

RESEARCH_SYSTEM_PROMPT = """You are producing entries for a technical weekly digest read by an ML/computational-biology practitioner with a pharmaceutical-science background. Be precise, technical, and concise. Do NOT re-explain basic ML or pharmacology concepts."""

RESEARCH_ITEM_TEMPLATE = """
--- ITEM {index} ---
Source type: {source_type}
Title: {title}
Text: {raw_text}
URL: {url}
"""

RESEARCH_USER_PROMPT = """For each of the following {count} papers/posts, produce a structured entry with exactly these sections:

1. ONE-LINE HEADLINE (plain, no hype)
2. WHAT'S NEW (2-3 sentences: what the authors actually did/found — separate from claims)
3. TECHNICAL INNOVATION (3-5 sentences, graduate-level ML background — specific architectural or methodological innovation, what changed vs prior approaches, why it works mechanistically)
4. CAVEATS (preprint status, sample size, benchmark limitations, anything evident from abstract/methods)
5. LINK: [include the URL]

Format your response as:

=== ITEM 1 ===
HEADLINE: ...
WHAT'S NEW: ...
TECHNICAL INNOVATION: ...
CAVEATS: ...
LINK: ...

=== ITEM 2 ===
... etc.

{items_text}
"""

EVENTS_JOBS_SYSTEM_PROMPT = """You are extracting structured information from event/job listings for a digest targeting someone with an AI + computational-biology + drug-discovery background. Be concise."""

EVENTS_JOBS_ITEM_TEMPLATE = """
--- ITEM {index} ---
Type: {section}
Title: {title}
Text: {raw_text}
URL: {url}
"""

EVENTS_JOBS_USER_PROMPT = """For each of the following {count} listings, extract:

1. NAME: event or job title
2. DATE: date or posting date (if available)
3. LOCATION: specify if virtual/Singapore/elsewhere
4. ORGANIZER/EMPLOYER: who is hosting or hiring
5. RELEVANCE NOTE: one line on why this matters for AI + computational-biology + drug-discovery

Format your response as:

=== ITEM 1 ===
NAME: ...
DATE: ...
LOCATION: ...
ORGANIZER/EMPLOYER: ...
RELEVANCE NOTE: ...

=== ITEM 2 ===
... etc.

{items_text}
"""


# ── Parsing ────────────────────────────────────────────────────────────────────

def _parse_research_response(response_text: str, items: list[RawItem]) -> list[SummarizedItem]:
    """Parse a batched research summarization response into SummarizedItem objects."""
    results: list[SummarizedItem] = []

    # Split by item delimiter
    item_blocks = re.split(r"===\s*ITEM\s*\d+\s*===", response_text)
    item_blocks = [b.strip() for b in item_blocks if b.strip()]

    for i, block in enumerate(item_blocks):
        if i >= len(items):
            break

        raw_item = items[i]

        # Extract fields
        headline = _extract_field(block, "HEADLINE")
        whats_new = _extract_field(block, "WHAT'S NEW")
        tech_innovation = _extract_field(block, "TECHNICAL INNOVATION")
        caveats = _extract_field(block, "CAVEATS")

        results.append(
            SummarizedItem(
                id=raw_item.id,
                section=raw_item.section,
                title=raw_item.title,
                url=raw_item.url,
                source_name=raw_item.source_name,
                published_at=raw_item.published_at,
                headline=headline or raw_item.title,
                whats_new=whats_new,
                technical_innovation=tech_innovation,
                caveats=caveats,
            )
        )

    return results


def _parse_events_jobs_response(response_text: str, items: list[RawItem]) -> list[SummarizedItem]:
    """Parse a batched events/jobs extraction response into SummarizedItem objects."""
    results: list[SummarizedItem] = []

    item_blocks = re.split(r"===\s*ITEM\s*\d+\s*===", response_text)
    item_blocks = [b.strip() for b in item_blocks if b.strip()]

    for i, block in enumerate(item_blocks):
        if i >= len(items):
            break

        raw_item = items[i]

        name = _extract_field(block, "NAME")
        date = _extract_field(block, "DATE")
        location = _extract_field(block, "LOCATION")
        organizer = _extract_field(block, "ORGANIZER/EMPLOYER")
        relevance = _extract_field(block, "RELEVANCE NOTE")

        results.append(
            SummarizedItem(
                id=raw_item.id,
                section=raw_item.section,
                title=raw_item.title,
                url=raw_item.url,
                source_name=raw_item.source_name,
                published_at=raw_item.published_at,
                name=name or raw_item.title,
                date=date or raw_item.published_at,
                location=location,
                organizer_or_employer=organizer,
                relevance_note=relevance,
            )
        )

    return results


def _extract_field(block: str, field_name: str) -> str:
    """Extract a named field from a response block.

    Handles variations in LLM output like:
    - HEADLINE: value
    - **HEADLINE**: value
    - HEADLINE:\nvalue
    - 1. HEADLINE: value
    """
    # Known field markers that signal the start of the next field
    all_fields = [
        "HEADLINE", "WHAT'S NEW", "WHATS NEW", "WHAT\u2019S NEW",
        "TECHNICAL INNOVATION", "CAVEATS", "LINK",
        "NAME", "DATE", "LOCATION", "ORGANIZER/EMPLOYER",
        "ORGANIZER", "EMPLOYER", "RELEVANCE NOTE",
    ]

    # Build pattern: field_name possibly wrapped in ** or preceded by numbers
    # Capture everything until the next known field or end of block
    escaped_name = re.escape(field_name)
    # Match field_name with optional bold markers, numbering, colons
    field_pattern = rf"(?:\d+\.?\s*)?(?:\*\*)?{escaped_name}(?:\*\*)?[\s:]*"

    # Build lookahead for the next field
    next_fields = [re.escape(f) for f in all_fields if f.upper() != field_name.upper()]
    next_field_pattern = "|".join(
        rf"(?:\d+\.?\s*)?(?:\*\*)?{nf}(?:\*\*)?[\s:]"
        for nf in next_fields
    )
    # Match until next field or end
    if next_field_pattern:
        pattern = rf"{field_pattern}(.*?)(?={next_field_pattern}|$)"
    else:
        pattern = rf"{field_pattern}(.*?)$"

    match = re.search(pattern, block, re.DOTALL | re.IGNORECASE)
    if match:
        value = match.group(1).strip()
        # Clean up any trailing/leading artifacts
        value = re.sub(r"^[:\-\s]+", "", value)
        value = value.strip()
        return value
    return ""


# ── Core summarization ─────────────────────────────────────────────────────────

def _get_source_type(source_name: str) -> str:
    """Map source name to source type for the prompt."""
    source_lower = source_name.lower()
    if "arxiv" in source_lower or "biorxiv" in source_lower or "medrxiv" in source_lower:
        return "preprint"
    if "pubmed" in source_lower:
        return "peer-reviewed"
    if "linkedin" in source_lower or "hacker news" in source_lower:
        return "social"
    return "blog"


def _summarize_research_batch(client: anthropic.Anthropic, batch: list[RawItem]) -> list[SummarizedItem]:
    """Summarize a batch of research items in a single API call."""
    items_text = ""
    for i, item in enumerate(batch, 1):
        items_text += RESEARCH_ITEM_TEMPLATE.format(
            index=i,
            source_type=_get_source_type(item.source_name),
            title=item.title,
            raw_text=item.raw_text,
            url=item.url,
        )

    user_prompt = RESEARCH_USER_PROMPT.format(count=len(batch), items_text=items_text)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=RESEARCH_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        response_text = response.content[0].text
        return _parse_research_response(response_text, batch)
    except Exception as exc:
        logger.error("Summarize research batch failed: %s", exc)
        # Fallback: use raw titles as summaries
        return [
            SummarizedItem(
                id=item.id,
                section=item.section,
                title=item.title,
                url=item.url,
                source_name=item.source_name,
                published_at=item.published_at,
                headline=item.title,
                whats_new=item.raw_text[:200],
                technical_innovation="(Summarization failed — see original)",
                caveats="",
            )
            for item in batch
        ]


def _summarize_events_jobs_batch(client: anthropic.Anthropic, batch: list[RawItem]) -> list[SummarizedItem]:
    """Summarize a batch of events/jobs items in a single API call."""
    items_text = ""
    for i, item in enumerate(batch, 1):
        items_text += EVENTS_JOBS_ITEM_TEMPLATE.format(
            index=i,
            section=item.section,
            title=item.title,
            raw_text=item.raw_text,
            url=item.url,
        )

    user_prompt = EVENTS_JOBS_USER_PROMPT.format(count=len(batch), items_text=items_text)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=EVENTS_JOBS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        response_text = response.content[0].text
        return _parse_events_jobs_response(response_text, batch)
    except Exception as exc:
        logger.error("Summarize events/jobs batch failed: %s", exc)
        # Fallback
        return [
            SummarizedItem(
                id=item.id,
                section=item.section,
                title=item.title,
                url=item.url,
                source_name=item.source_name,
                published_at=item.published_at,
                name=item.title,
                date=item.published_at,
                location="(extraction failed)",
                organizer_or_employer="",
                relevance_note="",
            )
            for item in batch
        ]


def summarize(items: list[RawItem], dry_run: bool = False) -> list[SummarizedItem]:
    """Summarize all items using Claude Haiku, batched for efficiency.

    Args:
        items: Ranked and capped items.
        dry_run: If True, skip LLM calls and return stub summaries.

    Returns:
        List of SummarizedItem objects.
    """
    if dry_run:
        logger.info("Summarize: dry run — returning stub summaries for %d items", len(items))
        results: list[SummarizedItem] = []
        for item in items:
            if item.section == "research":
                results.append(SummarizedItem(
                    id=item.id, section=item.section, title=item.title,
                    url=item.url, source_name=item.source_name,
                    published_at=item.published_at,
                    headline=item.title,
                    whats_new=item.raw_text[:150] + "...",
                    technical_innovation="[Dry run — no LLM call]",
                    caveats="[Dry run]",
                ))
            else:
                results.append(SummarizedItem(
                    id=item.id, section=item.section, title=item.title,
                    url=item.url, source_name=item.source_name,
                    published_at=item.published_at,
                    name=item.title, date=item.published_at,
                    location="[Dry run]",
                    organizer_or_employer="[Dry run]",
                    relevance_note="[Dry run — no LLM call]",
                ))
        return results

    # Initialize Anthropic client
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("Summarize: ANTHROPIC_API_KEY not set")
        raise ValueError("ANTHROPIC_API_KEY environment variable is required")

    client = anthropic.Anthropic(api_key=api_key)

    research = [i for i in items if i.section == "research"]
    events_jobs = [i for i in items if i.section in ("events", "jobs")]

    results: list[SummarizedItem] = []

    # Process research in batches
    for i in range(0, len(research), RESEARCH_BATCH_SIZE):
        batch = research[i : i + RESEARCH_BATCH_SIZE]
        logger.info("Summarize: research batch %d-%d of %d", i + 1, i + len(batch), len(research))
        batch_results = _summarize_research_batch(client, batch)
        results.extend(batch_results)

    # Process events/jobs in batches
    for i in range(0, len(events_jobs), EVENTS_JOBS_BATCH_SIZE):
        batch = events_jobs[i : i + EVENTS_JOBS_BATCH_SIZE]
        logger.info("Summarize: events/jobs batch %d-%d of %d", i + 1, i + len(batch), len(events_jobs))
        batch_results = _summarize_events_jobs_batch(client, batch)
        results.extend(batch_results)

    logger.info("Summarize: completed %d items", len(results))
    return results
