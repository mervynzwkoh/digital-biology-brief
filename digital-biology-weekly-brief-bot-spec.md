# Digital Biology Weekly Brief Bot — Technical Design & Build Spec

**Purpose of this document:** This is a complete build specification for an autonomous, near-zero-cost weekly research/events/jobs brief, delivered via Telegram, covering ML for drug discovery, protein structure prediction/design, virtual cell modelling, and the underlying model architectures behind them. It is written to be handed directly to a coding agent (e.g. Claude Code) as the implementation prompt — it specifies architecture, data sources with real free endpoints, module boundaries, schemas, prompts, and a milestone-ordered build plan.

---

## 1. Goals & Constraints

**Goals**
1. Weekly automated brief delivered via a Telegram bot, covering three sections:
   - **Frontier Research** — new papers/preprints/blog posts on ML architectures applied to drug discovery, protein structure/design, and virtual cell simulation. Each item gets a short summary *and* a deeper explanation of the technical innovation, plus a link.
   - **Events** — conferences, workshops, meetups, online or in Singapore.
   - **Jobs** — Singapore-based roles in AI/computational biology/drug discovery.
2. Fully automated, scheduled, no manual triggering required.
3. Optimize hard for cost — target **$0/month infrastructure cost**, with the only variable cost being LLM summarization tokens (aim to keep this under ~$1/month).
4. Respect platform Terms of Service — no LinkedIn scraping via unofficial/automated login-based methods (see §5.4 for why, and the compliant alternative used instead).

**Non-goals**
- Not a real-time alerting system — weekly cadence only.
- Not a general-purpose research assistant — scoped to the topic areas above.
- Not scraping authenticated/paywalled content.

---

## 2. Architecture Overview

A single scheduled batch job, orchestrated for free by **GitHub Actions**, runs once a week. It has four stages:

```
┌─────────────┐    ┌──────────────┐    ┌────────────────┐    ┌──────────────┐
│  1. INGEST   │ →  │ 2. DEDUP &   │ →  │ 3. SUMMARIZE   │ →  │ 4. DELIVER   │
│ (pull from   │    │    RANK      │    │  (Claude Haiku │    │ (Telegram +  │
│  ~10 free    │    │ (state file  │    │   4.5, cheap   │    │  GitHub      │
│  sources)    │    │  in repo)    │    │   tier)        │    │  Pages)      │
└─────────────┘    └──────────────┘    └────────────────┘    └──────────────┘
```

- **Compute:** GitHub Actions (public repo → unlimited free minutes; private repo → 2,000 free minutes/month, which is far more than a weekly ~10-minute job needs).
- **State/storage:** No database service. State (which items have already been seen/sent) is a JSON file committed back into the repo by the workflow itself. Zero infra, zero cost, fully version-controlled and human-inspectable.
- **LLM:** Anthropic API, `claude-haiku-4-5` for summarization/synthesis. At current published pricing ($1/MTok in, $5/MTok out), a weekly run processing ~30-50 short items should cost a few cents to low tens of cents per run — call it **under $1/month**. This is the only line item that isn't literally free; everything else is.
- **Delivery:** Telegram Bot API (free, no rate-limit-relevant cost at this volume) sends a condensed digest. The *detailed* explanations (which can be long) are rendered to a static HTML page hosted on **GitHub Pages** (free for public repos), and the Telegram message links to it. This avoids Telegram's 4096-character message limit and gives you a nicely readable, archivable weekly page.

---

## 3. Data Sources (all free, no LinkedIn login automation)

### 3.1 Frontier Research

| Source | Access method | Notes |
|---|---|---|
| arXiv | Official API (`export.arxiv.org/api/query`), no key | Query categories `q-bio.*`, `cs.LG`, `cs.AI` with keyword filters (protein, virtual cell, transformer, diffusion, drug discovery, etc.) |
| bioRxiv / medRxiv | Public API (`api.biorxiv.org/details/[server]/[interval]`), no key | Filter by category (bioinformatics, genomics, synthetic biology) and keyword post-fetch |
| PubMed | NCBI E-utilities (`eutils.ncbi.nlm.nih.gov`), no key required (add an email/tool param per NCBI etiquette) | For peer-reviewed journal hits (Nature, Cell, Science family) |
| Semantic Scholar | Public API (`api.semanticscholar.org/graph/v1`), optional free API key for higher rate limits | Good for citation context and finding related/citing papers |
| Lab & company blogs | RSS feeds | Google DeepMind blog, Isomorphic Labs, Recursion, Insilico Medicine, Arc Institute, Broad Institute, NVIDIA (BioNeMo/healthcare tag), EvolutionaryScale, Chai Discovery, Xaira — most publish RSS or have feeds discoverable at `/feed` or `/rss.xml` |
| Journal TOC feeds | RSS | *Nature Methods*, *Nature Biotechnology*, *Nature Machine Intelligence*, *Cell Systems*, *NeurIPS/ICML proceedings* (via arXiv cross-listing) mostly expose free table-of-contents RSS |
| Hacker News | Algolia HN Search API (`hn.algolia.com/api/v1/search`), no key | Signal for what's getting technical discussion/hype — useful cross-check, not a primary source |
| "Social/blog chatter" proxy for LinkedIn | Google Programmable Search Engine (Custom Search JSON API) — **free tier: 100 queries/day** | Query restricted to `site:linkedin.com/posts OR site:linkedin.com/pulse` + topic keywords. This surfaces *public, indexed* LinkedIn posts without logging in or scraping — see §5.4 |

### 3.2 Events

| Source | Access method | Notes |
|---|---|---|
| Luma (lu.ma) | Most public calendars expose an `.ics` feed at a predictable URL; some organizers also have public API access | Track specific SG/biotech-AI community calendars you already follow |
| Eventbrite | Public event pages can be queried via Google CSE (`site:eventbrite.sg`) since Eventbrite's public search API access for third parties is limited | Treat as a search source, not a direct API |
| SG community sites | Lightweight, low-frequency (weekly) scraping of specific known pages — SGInnovate, BioSingapore, NUS/A*STAR seminar listing pages | Use `requests` + `BeautifulSoup`; respect `robots.txt`; weekly frequency is well within polite-use norms |
| Google CSE | Same 100/day free quota as above | Query `site:lu.ma OR site:eventbrite.sg Singapore AI biology drug discovery` |

### 3.3 Jobs (Singapore)

| Source | Access method | Notes |
|---|---|---|
| **MyCareersFuture** | Official public API: `https://api.mycareersfuture.gov.sg/v2/jobs` — **no auth, no key required**, confirmed public endpoint used by the government portal itself | This is Singapore's official job portal; salary disclosure is legally mandated so listings include pay ranges. Query with keywords like "computational biology", "bioinformatics", "machine learning", "drug discovery", filtered to SG. |
| Greenhouse job boards | Public API: `boards-api.greenhouse.io/v1/boards/{company}/jobs` | Free, no key, per-company. Maintain a config list of target companies (e.g. Recursion, Isomorphic Labs, Insilico Medicine, Genesis Therapeutics, Xaira, EvolutionaryScale) and check for SG-tagged or remote roles |
| Lever job boards | Public API: `api.lever.co/v0/postings/{company}` | Same pattern as Greenhouse, for companies using Lever |
| LinkedIn Jobs | **Not automated** — no compliant free API for third-party job search | See §5.4. Optionally surfaced via Google CSE as a search-result link only, never scraped |

---

## 4. Component Design

### 4.1 Repo layout

```
digital-biology-brief/
├── .github/workflows/weekly_brief.yml
├── config/
│   ├── keywords.yaml        # topic keyword lists per section
│   ├── companies.yaml       # Greenhouse/Lever company slugs to track
│   └── sources.yaml         # RSS feed URLs, arXiv categories, etc.
├── src/
│   ├── sources/
│   │   ├── arxiv.py
│   │   ├── biorxiv.py
│   │   ├── pubmed.py
│   │   ├── semantic_scholar.py
│   │   ├── rss_blogs.py
│   │   ├── hackernews.py
│   │   ├── google_cse.py
│   │   ├── events_sg.py
│   │   ├── mycareersfuture.py
│   │   └── ats_boards.py     # Greenhouse + Lever
│   ├── pipeline/
│   │   ├── dedupe.py         # loads/updates state/seen.json
│   │   ├── rank.py           # simple relevance scoring pre-LLM
│   │   ├── summarize.py      # Claude Haiku calls
│   │   └── render.py         # builds Telegram digest + GitHub Pages HTML
│   ├── delivery/
│   │   └── telegram_client.py
│   └── main.py                # orchestrates the 4 stages
├── state/
│   └── seen.json             # committed by the workflow after each run
├── docs/                       # GitHub Pages output (detailed weekly briefs)
│   └── briefs/YYYY-MM-DD.html
├── requirements.txt
└── README.md
```

### 4.2 Stage 1 — Ingest

Each `sources/*.py` module exposes a single function `fetch() -> list[RawItem]` where `RawItem` is a small dataclass:

```python
@dataclass
class RawItem:
    id: str            # stable dedupe key (DOI, arXiv id, URL hash, job_post_id, etc.)
    section: str        # "research" | "events" | "jobs"
    title: str
    url: str
    source_name: str
    published_at: str   # ISO date
    raw_text: str        # abstract / description / job description, truncated
```

`main.py` calls all fetchers, merges results per section, and passes them to stage 2.

### 4.3 Stage 2 — Dedupe & Rank

- Load `state/seen.json` (a dict of `id -> first_seen_date`).
- Drop any `RawItem` whose `id` is already present.
- Apply a lightweight pre-LLM relevance filter: keyword match against `config/keywords.yaml` (weighted — e.g. "protein structure", "diffusion model", "virtual cell", "GRPO", "foundation model", "geneformer", "ESM", "AlphaFold", "reinforcement learning" score higher than generic ML terms). This keeps LLM token spend down by not summarizing irrelevant matches.
- Cap each section to a sane top-N (e.g. top 12 research items, top 8 events, top 15 jobs) to control both LLM cost and brief length.
- After the run, write the new set of seen IDs back to `state/seen.json`; the workflow commits this file.

### 4.4 Stage 3 — Summarize (LLM layer)

This is where your existing structured-analysis habits should be encoded directly into the prompt, since that's the review depth you already apply manually to papers.

**Research item prompt template** (one Claude Haiku call per item, or batched — batching several items into one call with clear delimiters is more token-efficient and recommended given the volume):

```
You are producing one entry for a technical weekly digest read by an ML/computational-biology
practitioner with a pharmaceutical-science background. For the following paper/post, produce:

1. ONE-LINE HEADLINE (plain, no hype)
2. WHAT'S NEW (2-3 sentences: what the authors actually did/found — separate this clearly
   from what they claim it means)
3. TECHNICAL INNOVATION (3-5 sentences, assume graduate-level ML background — explain the
   specific architectural or methodological innovation: what changed vs prior approaches,
   why it works mechanistically. Do NOT re-explain basic ML or pharmacology concepts.)
4. CAVEATS (preprint status, sample size, benchmark limitations, anything the authors
   themselves flag or that is evident from the abstract/methods)
5. LINK: {url}

Source type: {preprint|peer-reviewed|blog|social}
Title: {title}
Text: {raw_text}
```

**Events/jobs items** need much lighter processing — mostly extraction/normalization rather than synthesis:
```
Extract from the following listing: event/job name, date (or posting date), location
(specify if virtual/Singapore/elsewhere), organizer/employer, one-line relevance note
for someone with an AI + computational-biology + drug-discovery background. Text: {raw_text}
```

Batch 5-8 items per API call using a numbered-list-in, numbered-list-out format to reduce call overhead and cost.

### 4.5 Stage 4 — Deliver

- **Detailed brief:** render all summarized items into a single HTML page (a plain Jinja2 template is enough — three sections, one subsection per item) and write it to `docs/briefs/YYYY-MM-DD.html`. Since `docs/` is published via GitHub Pages, this becomes a permanent, linkable, browsable archive at zero cost.
- **Telegram digest:** send a condensed message (headline + one-line summary + link, per item, grouped by section) via `sendMessage`, plus a top-line link to the full HTML brief for the deep technical explanations. If the digest itself is under ~4000 characters, send it as one message; otherwise split by section into 3 messages (one per section) to stay safely under Telegram's limit.

---

## 5. Practical & Legal Notes

### 5.1 Secrets
Store as GitHub Actions repository secrets (never commit to the repo):
- `ANTHROPIC_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_CX` (for the Custom Search JSON API)
- `NCBI_EMAIL` (E-utilities etiquette, not a secret but keep in config)

### 5.2 Telegram bot setup (one-time, manual)
1. Message `@BotFather` on Telegram → `/newbot` → get a bot token.
2. Message your new bot once (any text) so it can DM you, or add it to a private group.
3. Call `https://api.telegram.org/bot<token>/getUpdates` to find your `chat_id`.
4. Store both as GitHub secrets above.

### 5.3 Scheduling
`.github/workflows/weekly_brief.yml` uses a `schedule: cron:` trigger (GitHub Actions cron runs in UTC — offset to land at your preferred Singapore-time slot, e.g. `0 23 * * 0` for Monday 07:00 SGT) plus `workflow_dispatch:` so you can also trigger it manually for testing.

### 5.4 Why no LinkedIn scraping — and what to do instead
LinkedIn's Terms of Service prohibit automated scraping/data collection, and it actively detects and blocks unauthorized bots and login-based automation; there is no free official API for third-party content or job search. Building an automated scraper that logs into LinkedIn (directly or via unofficial libraries) carries real account-ban and ToS-violation risk, and isn't a good foundation for a tool you intend to run indefinitely. The design above avoids this entirely by using the Google Custom Search JSON API restricted to LinkedIn's own indexed public URLs (`site:linkedin.com/posts`, `/pulse`, `/jobs`) — this surfaces *links to* public LinkedIn content through a legitimate third-party search API, without touching LinkedIn's servers or authentication at all. It won't be as complete as full LinkedIn access, but it's compliant, free (100 queries/day), and durable.

If down the line you want denser LinkedIn coverage, the ToS-compliant path is LinkedIn's official Marketing/Talent APIs, which require a partner application and are not free — worth revisiting only if this becomes a serious ongoing tool rather than a personal digest.

### 5.5 Cost summary

| Component | Cost |
|---|---|
| GitHub Actions (compute) | $0 (public repo) |
| GitHub Pages (hosting) | $0 |
| State storage (JSON in repo) | $0 |
| arXiv / bioRxiv / PubMed / Semantic Scholar / HN APIs | $0 |
| MyCareersFuture / Greenhouse / Lever APIs | $0 |
| Google Custom Search JSON API | $0 up to 100 queries/day |
| Telegram Bot API | $0 |
| Anthropic API (Haiku 4.5, ~30-50 short items/week, batched calls) | ~$0.10–$1.00/month |
| **Total** | **effectively free**, sub-$1/month |

---

## 6. Build Plan (milestones for the coding agent)

1. **Scaffold repo** — directory layout above, `requirements.txt` (`requests`, `feedparser`, `beautifulsoup4`, `anthropic`, `jinja2`, `pyyaml`, `python-telegram-bot` or raw `requests` against the Bot API).
2. **Implement one source module fully** (start with `arxiv.py`) end-to-end through dedupe → a dry-run print, to validate the pipeline shape before building the rest.
3. **Implement remaining research sources** (`biorxiv.py`, `pubmed.py`, `semantic_scholar.py`, `rss_blogs.py`, `hackernews.py`, `google_cse.py`).
4. **Implement events sources** (`events_sg.py` — start with 3-5 known SG community pages/calendars in `config/sources.yaml`, plus `google_cse.py` reuse).
5. **Implement jobs sources** (`mycareersfuture.py`, `ats_boards.py` with a starter `companies.yaml` list).
6. **Implement dedupe/rank** against `state/seen.json`.
7. **Implement summarize.py** with the batched prompt templates in §4.4; unit-test against 2-3 real fetched items before wiring the full pipeline.
8. **Implement render.py** (Jinja2 → `docs/briefs/*.html`) and **telegram_client.py**.
9. **Wire `main.py`** end-to-end; run locally once with real secrets in a local `.env` (not committed) to validate a full dry run.
10. **Add the GitHub Actions workflow** (`weekly_brief.yml`): checkout → set up Python → install deps → run `main.py` with secrets injected as env vars → commit updated `state/seen.json` and new `docs/briefs/*.html` back to the repo → push.
11. **Enable GitHub Pages** on the repo (serve from `docs/` on `main`).
12. **Run manually via `workflow_dispatch` once**, inspect the Telegram message and the Pages brief, tune keyword lists and per-section item caps.
13. **Let the weekly cron take over.**

---

## 7. Example config schemas

`config/keywords.yaml`:
```yaml
research:
  high_weight:
    - "virtual cell"
    - "protein structure prediction"
    - "protein design"
    - "diffusion model"
    - "foundation model"
    - "geneformer"
    - "single-cell foundation model"
    - "reinforcement learning"
  medium_weight:
    - "drug discovery"
    - "molecular docking"
    - "binding affinity"
    - "transformer"
```

`config/companies.yaml`:
```yaml
greenhouse:
  - recursion
  - isomorphiclabs
lever:
  - xaira
```

---

This spec is intentionally source-and-schema-specific so a coding agent can implement it directly without needing to make architectural decisions — the main open choices left for you are the exact keyword lists, target company list, and which SG community event pages to track, all of which live in `config/` and can be edited without touching code.
