"""Deduplicate items against previously seen items stored in state/seen.json.

State file is a JSON dict mapping item IDs to first-seen dates.
Items older than 90 days are pruned to prevent unbounded growth.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.models import RawItem, STATE_DIR

logger = logging.getLogger(__name__)

SEEN_FILE = STATE_DIR / "seen.json"
PRUNE_DAYS = 90


def _load_seen() -> dict[str, str]:
    """Load the seen-items state file."""
    if not SEEN_FILE.exists():
        return {}
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load seen.json: %s — starting fresh", exc)
        return {}


def _save_seen(seen: dict[str, str]) -> None:
    """Write the seen-items state file."""
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, sort_keys=True)
    logger.info("Saved %d items to seen.json", len(seen))


def _prune_old(seen: dict[str, str]) -> dict[str, str]:
    """Remove entries older than PRUNE_DAYS to keep the file manageable."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=PRUNE_DAYS)).strftime("%Y-%m-%d")
    before = len(seen)
    seen = {k: v for k, v in seen.items() if v >= cutoff}
    pruned = before - len(seen)
    if pruned > 0:
        logger.info("Pruned %d old entries from seen.json", pruned)
    return seen


def filter_new(items: list[RawItem]) -> list[RawItem]:
    """Remove items that have already been seen.

    Args:
        items: All ingested items.

    Returns:
        Only items whose IDs are not in the seen state.
    """
    seen = _load_seen()
    new_items = [item for item in items if item.id not in seen]
    logger.info(
        "Dedupe: %d total items → %d new (filtered %d seen)",
        len(items),
        len(new_items),
        len(items) - len(new_items),
    )
    return new_items


def mark_seen(items: list[RawItem]) -> None:
    """Mark items as seen and persist the state.

    Call this AFTER successful delivery to ensure we don't mark items
    as seen if delivery failed.
    """
    seen = _load_seen()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for item in items:
        if item.id not in seen:
            seen[item.id] = today

    seen = _prune_old(seen)
    _save_seen(seen)
