# Digital Biology Weekly Brief Bot 🧬

An autonomous, near-zero-cost weekly research/events/jobs digest covering ML for drug discovery, protein structure prediction/design, virtual cell modelling, and the model architectures behind them.

**Delivered via Telegram** with detailed technical write-ups on **GitHub Pages**.

## How It Works

```
┌─────────────┐    ┌──────────────┐    ┌────────────────┐    ┌──────────────┐
│  1. INGEST   │ →  │ 2. DEDUPE &   │ →  │ 3. SUMMARIZE   │ →  │ 4. DELIVER   │
│ (pull from   │    │    RANK      │    │  (Claude Haiku │    │ (Telegram +  │
│  ~10 free    │    │ (state file  │    │   4.5)         │    │  GitHub      │
│  sources)    │    │  in repo)    │    │                │    │  Pages)      │
└─────────────┘    └──────────────┘    └────────────────┘    └──────────────┘
```

### Data Sources (all free)

**Research:** arXiv, bioRxiv/medRxiv, PubMed, Semantic Scholar, RSS blogs/journals, Hacker News, Google CSE (LinkedIn proxy)

**Events:** SG community pages, Luma calendars, Google CSE (Eventbrite/Luma)

**Jobs:** MyCareersFuture (SG gov API), Greenhouse & Lever job boards

## Setup

### 1. Clone & Install

```bash
git clone https://github.com/<your-username>/digital-biology-brief.git
cd digital-biology-brief
pip install -r requirements.txt
```

### 2. Configure Secrets

Create a `.env` file for local development (never committed):

```env
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=123456:ABC-...
TELEGRAM_CHAT_ID=your_chat_id
GOOGLE_CSE_API_KEY=AIza...
GOOGLE_CSE_CX=your_cx_id
NCBI_EMAIL=your@email.com
GITHUB_PAGES_URL=https://<username>.github.io/digital-biology-brief
```

For production, add these as **GitHub Actions repository secrets**.

### 3. Telegram Bot Setup

1. Message `@BotFather` on Telegram → `/newbot` → copy the bot token
2. Message your bot (any text) so it can DM you
3. Call `https://api.telegram.org/bot<token>/getUpdates` to find your `chat_id`

### 4. Google Custom Search

1. Go to [Programmable Search Engine](https://programmablesearchengine.google.com/)
2. Create a search engine (search the entire web)
3. Note your CX ID
4. Enable the Custom Search JSON API in Google Cloud Console
5. Create an API key

### 5. Run

```bash
# Dry run (no LLM calls, no Telegram)
python -m src.main --dry-run

# Full run
python -m src.main

# With verbose logging
python -m src.main --dry-run -v
```

### 6. GitHub Pages

Enable GitHub Pages in repo settings → Source: deploy from `docs/` on `main` branch.

### 7. Schedule

The GitHub Actions workflow runs automatically every Monday at 07:00 SGT. You can also trigger it manually via the Actions tab → "Run workflow".

## Configuration

All configuration lives in `config/` — edit without touching code:

- **`keywords.yaml`** — relevance keywords per section (high/medium weight)
- **`companies.yaml`** — Greenhouse/Lever company slugs to track for jobs
- **`sources.yaml`** — RSS feeds, arXiv categories, API params, section caps

## Cost

| Component | Cost |
|---|---|
| GitHub Actions | $0 |
| GitHub Pages | $0 |
| All APIs (arXiv, bioRxiv, PubMed, etc.) | $0 |
| Telegram Bot API | $0 |
| Anthropic API (Claude Haiku 4.5) | ~$0.10–$1.00/month |
| **Total** | **~$0–$1/month** |

## Architecture

```
digital-biology-brief/
├── .github/workflows/weekly_brief.yml   # Cron + manual trigger
├── config/                               # Editable configuration
│   ├── keywords.yaml
│   ├── companies.yaml
│   └── sources.yaml
├── src/
│   ├── sources/          # 10 source fetchers
│   ├── pipeline/         # dedupe, rank, summarize, render
│   ├── delivery/         # Telegram client
│   ├── templates/        # Jinja2 HTML templates
│   ├── models.py         # Shared data models
│   └── main.py           # Pipeline orchestrator
├── state/seen.json       # Dedup state (auto-committed)
├── docs/                  # GitHub Pages output
│   ├── index.html
│   └── briefs/YYYY-MM-DD.html
└── requirements.txt
```

## License

MIT
