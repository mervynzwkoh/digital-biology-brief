"""Render summarized items into HTML briefs and Telegram digest messages.

- HTML: Jinja2 templates → docs/briefs/YYYY-MM-DD.html (served via GitHub Pages)
- Telegram: condensed text digest, split by section if > 4000 chars
- Also maintains docs/index.html as an archive listing.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.models import SummarizedItem, DOCS_DIR, TEMPLATES_DIR

logger = logging.getLogger(__name__)


def _group_by_section(items: list[SummarizedItem]) -> dict[str, list[SummarizedItem]]:
    """Group items by section, maintaining order."""
    groups: dict[str, list[SummarizedItem]] = {
        "research": [],
        "events": [],
        "jobs": [],
    }
    for item in items:
        if item.section in groups:
            groups[item.section].append(item)
    return groups


# ── HTML Rendering ─────────────────────────────────────────────────────────────

def render_html(items: list[SummarizedItem], date_str: str | None = None) -> str:
    """Render a full HTML brief page and write it to docs/briefs/.

    Args:
        items: All summarized items.
        date_str: Override date string (YYYY-MM-DD). Defaults to today.

    Returns:
        The relative path to the generated HTML file (for linking).
    """
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    groups = _group_by_section(items)

    # Set up Jinja2
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )
    template = env.get_template("brief.html.j2")

    html_content = template.render(
        date=date_str,
        research_items=groups["research"],
        events_items=groups["events"],
        jobs_items=groups["jobs"],
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

    # Write to docs/briefs/
    briefs_dir = DOCS_DIR / "briefs"
    briefs_dir.mkdir(parents=True, exist_ok=True)
    output_path = briefs_dir / f"{date_str}.html"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info("HTML brief written to %s", output_path)

    # Update the archive index
    _update_index()

    return f"briefs/{date_str}.html"


def _update_index() -> None:
    """Regenerate the archive index page listing all briefs."""
    briefs_dir = DOCS_DIR / "briefs"
    if not briefs_dir.exists():
        return

    # Find all brief HTML files, sorted newest first
    brief_files = sorted(briefs_dir.glob("*.html"), reverse=True)
    briefs = [{"date": f.stem, "path": f"briefs/{f.name}"} for f in brief_files]

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )

    try:
        template = env.get_template("index.html.j2")
        html_content = template.render(
            briefs=briefs,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        )
    except Exception:
        # If template doesn't exist yet, create a simple index
        html_content = _simple_index(briefs)

    index_path = DOCS_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info("Archive index updated with %d briefs", len(briefs))


def _simple_index(briefs: list[dict]) -> str:
    """Generate a simple index page if templates aren't available."""
    links = "\n".join(
        f'<li><a href="{b["path"]}">{b["date"]}</a></li>' for b in briefs
    )
    return f"""<!DOCTYPE html>
<html><head><title>Digital Biology Weekly Brief — Archive</title></head>
<body><h1>Digital Biology Weekly Brief</h1><ul>{links}</ul></body></html>"""


# ── Telegram Digest ───────────────────────────────────────────────────────────

# Max items per section in the Telegram digest (keeps messages under 4096 chars)
TELEGRAM_MAX_RESEARCH = 8
TELEGRAM_MAX_EVENTS = 6
TELEGRAM_MAX_JOBS = 10


def _build_research_section(items: list[SummarizedItem]) -> str:
    """Build the research section text for Telegram."""
    if not items:
        return ""
    lines = ["\U0001f52c <b>Frontier Research</b>\n"]
    for item in items[:TELEGRAM_MAX_RESEARCH]:
        headline = item.headline or item.title
        lines.append(f"\u2022 <b>{_escape_html(headline)}</b>")
        if item.whats_new:
            first_sentence = item.whats_new.split(". ")[0] + "."
            lines.append(f"  {_escape_html(first_sentence)}")
        lines.append(f'  <a href="{item.url}">\u2192 Read</a>\n')
    remaining = len(items) - TELEGRAM_MAX_RESEARCH
    if remaining > 0:
        lines.append(f"<i>... and {remaining} more in the full brief</i>\n")
    return "\n".join(lines)


def _build_events_section(items: list[SummarizedItem]) -> str:
    """Build the events section text for Telegram."""
    if not items:
        return ""
    lines = ["\U0001f4c5 <b>Events</b>\n"]
    for item in items[:TELEGRAM_MAX_EVENTS]:
        name = item.name or item.title
        location = f" ({_escape_html(item.location)})" if item.location else ""
        date_info = f" \u2014 {_escape_html(item.date)}" if item.date else ""
        lines.append(f"\u2022 <b>{_escape_html(name)}</b>{date_info}{location}")
        if item.relevance_note:
            lines.append(f"  {_escape_html(item.relevance_note)}")
        lines.append(f'  <a href="{item.url}">\u2192 Details</a>\n')
    return "\n".join(lines)


def _build_jobs_section(items: list[SummarizedItem]) -> str:
    """Build the jobs section text for Telegram."""
    if not items:
        return ""
    lines = ["\U0001f4bc <b>Jobs</b>\n"]
    for item in items[:TELEGRAM_MAX_JOBS]:
        name = item.name or item.title
        employer = f" @ {_escape_html(item.organizer_or_employer)}" if item.organizer_or_employer else ""
        location = f" ({_escape_html(item.location)})" if item.location else ""
        lines.append(f"\u2022 <b>{_escape_html(name)}</b>{employer}{location}")
        if item.relevance_note:
            lines.append(f"  {_escape_html(item.relevance_note)}")
        lines.append(f'  <a href="{item.url}">\u2192 Apply</a>\n')
    return "\n".join(lines)


def render_telegram_digest(
    items: list[SummarizedItem],
    brief_url: str,
    date_str: str | None = None,
) -> list[str]:
    """Render a condensed Telegram digest message.

    Args:
        items: All summarized items.
        brief_url: URL to the full HTML brief on GitHub Pages.
        date_str: Override date string. Defaults to today.

    Returns:
        List of message strings, each guaranteed to be valid HTML under 4096 chars.
    """
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    groups = _group_by_section(items)

    # Header — included at the top of EVERY message so the link is always visible
    header = (
        f"\U0001f9ec <b>Digital Biology Weekly Brief \u2014 {date_str}</b>\n\n"
        f'\U0001f4d6 <a href="{brief_url}">Full brief with technical details \u2192</a>\n\n'
    )

    # Build section texts
    research_text = _build_research_section(groups["research"])
    events_text = _build_events_section(groups["events"])
    jobs_text = _build_jobs_section(groups["jobs"])

    # Try single message first
    full_message = header + research_text + events_text + jobs_text
    if len(full_message) < 4000:
        return [full_message]

    # Split into separate messages — each gets the header with the Pages link
    messages: list[str] = []
    for section_text in (research_text, events_text, jobs_text):
        if not section_text:
            continue
        msg = header + section_text
        # Safety: if still too long, drop items from the end (never truncate mid-tag)
        if len(msg) > 4000:
            msg = header + section_text.rsplit("\n\n", 1)[0] + "\n\n<i>(see full brief for more)</i>"
        messages.append(msg)

    return messages if messages else [header + "<i>No items this week.</i>"]


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
