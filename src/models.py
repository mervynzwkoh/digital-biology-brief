"""Shared data models and configuration utilities for the Digital Biology Weekly Brief."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ── Paths ──────────────────────────────────────────────────────────────────────

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
STATE_DIR = ROOT_DIR / "state"
DOCS_DIR = ROOT_DIR / "docs"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class RawItem:
    """A single item ingested from any source, before deduplication or summarization."""

    id: str              # stable dedupe key (DOI, arXiv id, URL hash, job_post_id, etc.)
    section: str         # "research" | "events" | "jobs"
    title: str
    url: str
    source_name: str
    published_at: str    # ISO date string  (YYYY-MM-DD)
    raw_text: str        # abstract / description / job description, truncated to ~2000 chars


@dataclass
class SummarizedItem:
    """Post-LLM summarized item, ready for rendering."""

    id: str
    section: str
    title: str
    url: str
    source_name: str
    published_at: str

    # Research-specific (populated by summarize.py)
    headline: str = ""
    whats_new: str = ""
    technical_innovation: str = ""
    caveats: str = ""

    # Events / Jobs (populated by summarize.py)
    name: str = ""
    date: str = ""
    location: str = ""
    organizer_or_employer: str = ""
    relevance_note: str = ""

    # Relevance score from rank.py (carried through for potential use in rendering)
    score: float = 0.0


# ── Config loading ─────────────────────────────────────────────────────────────

def load_config(filename: str) -> dict[str, Any]:
    """Load a YAML config file from the config/ directory."""
    path = CONFIG_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_keywords() -> dict[str, Any]:
    """Load keyword configuration."""
    return load_config("keywords.yaml")


def load_companies() -> dict[str, Any]:
    """Load company slug configuration."""
    return load_config("companies.yaml")


def load_sources() -> dict[str, Any]:
    """Load source endpoint configuration."""
    return load_config("sources.yaml")
