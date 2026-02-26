# OSS Opportunities Radar

An autonomous Python agent that monitors four developer platforms, extracts genuine open source maintainer pain points, ranks them by signal strength, and delivers curated intelligence via email — requiring zero interaction after initial setup.

Set it up once, point it at your inbox, and forget it exists. Every morning a dark-mode email lands with the 5 highest-signal OSS pain points. Fridays bring the weekly trends. No dashboard. No buttons. Just signal.

---

## Architecture

```
launchd / GitHub Actions (survives reboots, zero intervention)
  └── radar schedule
       ├── Daily job (2x) ── scrape → filter → rank → [LLM summarize] → store → email
       ├── Weekly job (Fri) ── aggregate → trend analysis → email digest
       ├── LLM Backend ───── GitHub Models API → Amplifier CLI fallback (opt-in)
       └── State Store ────── SQLite catalog (WAL mode, 3 tables)

┌──────────────────────────────────────────────────────────────┐
│  Entry Points: CLI (Typer) │ APScheduler │ GitHub Actions    │
└──────────────────────────┬───────────────────────────────────┘
                           │
               ┌───────────▼───────────┐
               │    pipeline.py        │
               │  PipelineOrchestrator │
               └───────────┬───────────┘
                           │
         ┌─────────────────▼──────────────────┐
         │           Scraping Layer            │
         │  HN │ Dev.to │ Lobsters │ Reddit   │
         └─────────────────┬──────────────────┘
                           │ List[RawPost]
         ┌─────────────────▼──────────────────┐
         │  Ranking Layer                      │
         │  1. KeywordFilter (100+ patterns)   │
         │  2. MaintainerContextFilter         │
         │  3. SentimentFilter (VADER+TextBlob)│
         │  4. SignalScorer (batch-normalised) │
         └─────────────────┬──────────────────┘
                           │ List[ScoredPost]
         ┌─────────────────▼──────────────────┐
         │  LLM Summarizer (opt-in)           │
         │  GitHub Models → Amplifier fallback │
         └─────────────────┬──────────────────┘
                           │
         ┌─────────────────▼──────────────────┐
         │  BackfillManager (Fallback Ladder)  │
         │  live → archive-7d → archive-30d   │
         │  → partial                         │
         └─────────────────┬──────────────────┘
                           │
         ┌─────────────────▼──────────────────┐
         │  Storage: SQLite WAL (3 tables)     │
         └─────────────────┬──────────────────┘
                           │
         ┌─────────────────▼──────────────────┐
         │  Email: Jinja2 → SMTP (STARTTLS)   │
         └────────────────────────────────────┘
```

---

## Quick Start

### Path A: Local Daemon (macOS, one command)

```bash
cd ~/dev/oss-radar
bash install.sh
# Edit .env with your SMTP credentials
# Done. Daemon runs 2x/day + weekly digest. Check logs: tail -f logs/radar-stdout.log
```

### Path B: GitHub Actions (cloud, zero infra)

1. Push this repo to GitHub
2. Add secrets: `RADAR_SMTP_HOST`, `RADAR_SMTP_PORT`, `RADAR_SMTP_USER`, `RADAR_SMTP_PASSWORD`, `RADAR_EMAIL_FROM`, `RADAR_EMAIL_TO`
3. Optionally: `RADAR_REDDIT_CLIENT_ID`, `RADAR_REDDIT_CLIENT_SECRET`, `RADAR_LLM_ENABLED=true`
4. Daily scans run at **6 AM + 6 PM PST** (14:00 + 02:00 UTC)
5. Weekly digest runs **Friday 12 PM PST** (20:00 UTC)

### Path C: Manual

```bash
pip install -r requirements.txt
cp .env.example .env && nano .env
radar daily        # one-shot daily report
radar schedule     # start daemon
```

---

## CLI Reference

| Command | Description | Key Flags |
|---|---|---|
| `radar synth` | Full pipeline with synthetic data (no API keys) | `--count N`, `--seed N`, `--dry-run`, `--no-email` |
| `radar scrape` | Scrape all platforms, store raw posts | `--db-path` |
| `radar daily` | Full daily pipeline: scrape→filter→rank→email | `--force`, `--dry-run`, `--no-email` |
| `radar weekly` | Weekly digest from past 7 days of reports | `--dry-run`, `--no-email` |
| `radar validate` | Check DB, HTTP, SMTP connectivity | `--db-path` |
| `radar schedule` | Start APScheduler daemon | |
| `radar report` | Display a specific report | `--id ID` |
| `radar stats` | Show catalog statistics | `--db-path` |

**Global flags** (all commands): `--db-path PATH`, `--log-level LEVEL`

**Exit codes**:
- `0` — full success
- `1` — partial (< 5 posts, or SMTP retry exhausted)
- `2` — fatal failure (all scrapers failed, DB unwritable, unhandled exception)

---

## LLM Summarization (Opt-in)

Enable AI-powered one-sentence summaries for each pain point in your email reports.

```bash
# In .env
RADAR_LLM_ENABLED=true
RADAR_LLM_MODEL=claude-sonnet-4.6  # or any GitHub Models / Amplifier model
```

**How it works:**
- Primary: GitHub Models API via `gh api /models/chat/completions`
- Fallback: Amplifier CLI via `uv run amplifier`
- Graceful degradation: if both fail, falls back to 120-char body excerpt
- Zero new pip dependencies (pure stdlib async subprocess)

**Requirements:** Either `gh` CLI authenticated or Amplifier installed at `~/amplifier`.

---

## Synthetic Mode (No API Keys)

Run the full pipeline with realistic fake data — perfect for development, demos, and CI:

```bash
radar synth --no-email           # 50 synthetic posts, full pipeline
radar synth --seed 42 --count 100 --no-email  # reproducible
radar synth --dry-run            # no DB writes, no email
```

Synthetic posts use real pain keywords from the ranking module, so they exercise the full filter → score → backfill → store pipeline. ~60% pass all 3 filter layers, ~40% are intentional noise.

---

## Scoring Formula

```
influence_norm  = log10(author_karma + 1) / log10(max_karma + 1)   [0, 1]
engagement_norm = log10(score + comments + 1) / log10(max_eng + 1) [0, 1]

base_score     = 0.4 × influence_norm + 0.6 × engagement_norm
pain_factor    = 1.0 (1 keyword match) | 1.2 (2–3 matches) | 1.5 (4+ matches)
maintainer_boost = 1.0 (1 context signal) | 1.25 (2+ signals)
signal_score   = base_score × pain_factor × (1.0 + |sentiment_score|) × maintainer_boost
```

---

## Signal Filtering

Posts must pass **all three** layers:

1. **Keyword Gate** — title+body must match ≥1 of 100+ compiled regex patterns across 15 `PainCategory` enums
2. **Maintainer Context** — post must contain ≥1 signal: "I maintain", "my project", "we merged", "released v…", etc.
3. **Sentiment** — `(VADER × 0.6) + (TextBlob × 0.4) < −0.05` (only pain posts pass)

---

## Configuration Reference

All environment variables are prefixed `RADAR_`. See `.env.example` for the complete list.

| Variable | Default | Description |
|---|---|---|
| `RADAR_DB_PATH` | `~/.radar/catalog.db` | SQLite catalog path |
| `RADAR_EMAIL_ENABLED` | `false` | Enable email dispatch |
| `RADAR_SMTP_HOST` | `localhost` | SMTP server hostname |
| `RADAR_SMTP_PORT` | `587` | SMTP server port |
| `RADAR_SMTP_USER` | `""` | SMTP username |
| `RADAR_SMTP_PASSWORD` | `""` | SMTP password |
| `RADAR_EMAIL_TO` | `""` | Comma-separated recipients |
| `RADAR_REDDIT_ENABLED` | `false` | Enable Reddit scraper |
| `RADAR_REDDIT_CLIENT_ID` | `""` | Reddit API client ID |
| `RADAR_REDDIT_CLIENT_SECRET` | `""` | Reddit API client secret |
| `RADAR_INFLUENCE_WEIGHT` | `0.4` | Influence signal weight (must sum to 1.0 with engagement) |
| `RADAR_ENGAGEMENT_WEIGHT` | `0.6` | Engagement signal weight |
| `RADAR_DAILY_CRON` | `0 14,2 * * *` | Daily run cron (UTC) — 6 AM + 6 PM PST |
| `RADAR_WEEKLY_CRON` | `0 20 * * 5` | Weekly digest cron (UTC) |
| `RADAR_DUPLICATE_RUN_HOURS` | `10` | Duplicate-run guard window (safe for 2x/day) |
| `RADAR_LLM_ENABLED` | `false` | Enable LLM pain-point summaries |
| `RADAR_LLM_MODEL` | `claude-sonnet-4.6` | Model for LLM summarization |
| `RADAR_LOG_LEVEL` | `INFO` | Logging verbosity |
| `RADAR_LOG_JSON` | `false` | JSON log format for CI |

---

## Deployment

### launchd (macOS)

The installer creates a persistent `launchd` agent that:
- Runs `radar schedule` as a KeepAlive daemon (survives reboots)
- Executes 2x/day scans (6 AM + 6 PM PST) + Friday weekly digest
- Logs to `logs/` in the project directory

```bash
# Install
bash install.sh

# View logs
tail -f logs/radar-stdout.log

# Manual run
.venv/bin/radar daily --force

# Stop agent
launchctl bootout gui/$(id -u)/com.dubsopenhub.oss-radar

# Restart agent
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.dubsopenhub.oss-radar.plist
```

### GitHub Actions (cloud)

Two workflow files in `.github/workflows/`:
- **`daily.yml`** — 2x/day cron: `0 14 * * *` + `0 2 * * *`
- **`weekly.yml`** — Friday cron: `0 20 * * 5`

Both persist the SQLite catalog as a GitHub Actions artifact (90-day retention) and auto-create Issues on failure.

---

## Development

```bash
# Run tests (185 tests, no API keys needed)
pytest -x

# Run with coverage
pytest --cov=radar --cov-report=html

# Lint
ruff check .
```
