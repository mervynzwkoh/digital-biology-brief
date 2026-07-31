"""Digital Biology Weekly Brief — main orchestrator.

Runs the 4-stage pipeline:
  1. Ingest  → pull items from ~10 free sources
  2. Dedupe & Rank → filter seen items, score, cap per section
  3. Summarize → Claude Haiku batched calls
  4. Deliver → Telegram digest + GitHub Pages HTML

Usage:
    python -m src.main              # full run (requires secrets)
    python -m src.main --dry-run    # skip LLM + Telegram, print to stdout
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

# Load .env for local development (harmless in CI)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.models import RawItem
from src.pipeline.dedupe import filter_new, mark_seen
from src.pipeline.rank import rank_and_cap
from src.pipeline.summarize import summarize
from src.pipeline.render import render_html, render_telegram_digest
from src.delivery.telegram_client import send_digest

# Import all source fetchers
from src.sources import (
    arxiv,
    biorxiv,
    pubmed,
    semantic_scholar,
    rss_blogs,
    hackernews,
    google_cse,
    events_sg,
    mycareersfuture,
    ats_boards,
)

logger = logging.getLogger(__name__)

# All source modules to call, in order
SOURCE_FETCHERS = [
    ("arXiv", arxiv.fetch),
    ("bioRxiv/medRxiv", biorxiv.fetch),
    ("PubMed", pubmed.fetch),
    ("Semantic Scholar", semantic_scholar.fetch),
    ("RSS Blogs", rss_blogs.fetch),
    ("Hacker News", hackernews.fetch),
    ("Google CSE", google_cse.fetch),
    ("Events SG", events_sg.fetch),
    ("MyCareersFuture", mycareersfuture.fetch),
    ("ATS Boards", ats_boards.fetch),
]


def _setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def run(dry_run: bool = False, verbose: bool = False) -> None:
    """Execute the full pipeline."""
    _setup_logging(verbose)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info("=" * 60)
    logger.info("Digital Biology Weekly Brief — %s", date_str)
    logger.info("Mode: %s", "DRY RUN" if dry_run else "LIVE")
    logger.info("=" * 60)

    # ── Stage 1: Ingest ────────────────────────────────────────────────────────
    logger.info("── Stage 1: Ingest ──")
    all_items: list[RawItem] = []

    for name, fetcher in SOURCE_FETCHERS:
        try:
            items = fetcher()
            all_items.extend(items)
            logger.info("  [OK] %s: %d items", name, len(items))
        except Exception as exc:
            logger.error("  [FAIL] %s: failed - %s", name, exc)
            # Individual source failures don't kill the run

    logger.info("  Total ingested: %d items", len(all_items))

    if not all_items:
        logger.warning("No items ingested from any source — exiting")
        return

    # ── Stage 2: Dedupe & Rank ─────────────────────────────────────────────────
    logger.info("── Stage 2: Dedupe & Rank ──")
    new_items = filter_new(all_items)

    if not new_items:
        logger.info("No new items after deduplication — nothing to send")
        return

    ranked_items = rank_and_cap(new_items)
    logger.info("  Items after ranking/capping: %d", len(ranked_items))

    # ── Stage 3: Summarize ─────────────────────────────────────────────────────
    logger.info("── Stage 3: Summarize ──")
    summarized = summarize(ranked_items, dry_run=dry_run)
    logger.info("  Summarized: %d items", len(summarized))

    # ── Stage 4: Deliver ───────────────────────────────────────────────────────
    logger.info("── Stage 4: Deliver ──")

    # 4a. Render HTML brief
    brief_relative_path = render_html(summarized, date_str)
    logger.info("  HTML brief: %s", brief_relative_path)

    # Build the GitHub Pages URL (will be correct once Pages is enabled)
    # Uses the GITHUB_PAGES_URL env var if set, otherwise a placeholder
    pages_base = os.environ.get("GITHUB_PAGES_URL", "https://<username>.github.io/digital-biology-brief")
    brief_url = f"{pages_base}/{brief_relative_path}"

    # 4b. Render and send Telegram digest
    messages = render_telegram_digest(summarized, brief_url, date_str)

    if dry_run:
        logger.info("  [DRY RUN] Telegram messages that would be sent:")
        for i, msg in enumerate(messages, 1):
            # Strip HTML tags for readable console output
            import re
            clean = re.sub(r"<[^>]+>", "", msg)
            # Handle emoji/Unicode on Windows consoles that use cp1252
            safe_text = clean.encode("ascii", errors="replace").decode("ascii")
            print(f"\n{'-' * 40}")
            print(f"Message {i} ({len(msg)} chars):")
            print(f"{'-' * 40}")
            print(safe_text)
    else:
        success = send_digest(messages)
        if success:
            logger.info("  [OK] Telegram digest sent")
        else:
            logger.error("  [FAIL] Telegram digest failed")

    # ── Mark items as seen (after successful delivery) ─────────────────────────
    mark_seen(ranked_items)
    logger.info("  Marked %d items as seen", len(ranked_items))

    logger.info("=" * 60)
    logger.info("Done! Brief: %s", brief_url)
    logger.info("=" * 60)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Digital Biology Weekly Brief — automated research/events/jobs digest"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip LLM calls and Telegram delivery; print to stdout instead",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug-level logging",
    )
    args = parser.parse_args()

    run(dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
