# OSS Opportunities Radar

A production-ready Python daemon that monitors four developer platforms daily, extracts genuine open source maintainer pain points, ranks them by signal strength, persists them in a local catalog, and delivers curated intelligence via email — requiring zero interaction after initial setup.

---

## Architecture

```
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

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env — fill in SMTP credentials and optionally Reddit API keys

# 3. Run daily report
radar daily

# 4. Validate connectivity
radar validate

# 5. Start scheduler daemon
radar schedule
```

---

## CLI Reference

| Command | Description | Key Flags |
|---|---|---|
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

## Pain Categories (15)

| Category | Description |
|---|---|
| `burnout` | Maintainer exhaustion and quitting signals |
| `funding` | Sustainability, donations, sponsorship |
| `toxic_users` | Harassment, abuse, entitled users |
| `maintenance_burden` | Issue backlogs, legacy code, tech debt |
| `dependency_hell` | Version conflicts, transitive deps |
| `security_pressure` | CVEs, vulnerability disclosures |
| `breaking_changes` | API breaks, semver violations |
| `documentation` | Missing, wrong, or stale docs |
| `contributor_friction` | High barriers to contribution |
| `corporate_exploitation` | Free-riding, license violations |
| `scope_creep` | Feature bloat, out-of-scope requests |
| `tooling_fatigue` | Build tool chaos, CI failures |
| `governance` | Decision-making, CoC, forks |
| `abuse` | Spam, DMCA, legal threats |
| `ci_cd` | Broken pipelines, flaky tests |

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
| `RADAR_DAILY_CRON` | `0 16 * * *` | Daily run cron (UTC) |
| `RADAR_WEEKLY_CRON` | `0 20 * * 5` | Weekly digest cron (UTC) |
| `RADAR_DUPLICATE_RUN_HOURS` | `20` | Duplicate-run guard window |
| `RADAR_LOG_LEVEL` | `INFO` | Logging verbosity |
| `RADAR_LOG_JSON` | `false` | JSON log format for CI |

---

## Deployment Guide

### GitHub Actions (Recommended)

1. Fork this repo
2. Add secrets in **Settings → Secrets → Actions**:
   - `RADAR_SMTP_HOST`, `RADAR_SMTP_PORT`, `RADAR_SMTP_USER`, `RADAR_SMTP_PASSWORD`
   - `RADAR_EMAIL_FROM`, `RADAR_EMAIL_TO`
   - Optionally: `RADAR_REDDIT_CLIENT_ID`, `RADAR_REDDIT_CLIENT_SECRET`
3. The daily workflow runs at **08:00 AM PST** (16:00 UTC)
4. The weekly digest runs **every Friday at 12:00 PM PST** (20:00 UTC)

### Self-hosted Daemon

```bash
# Install in a venv
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env && nano .env

# Start daemon (runs daily + weekly jobs indefinitely)
radar schedule
```

### Manual crontab

```bash
# Edit crontab
crontab -e

# Add daily at 8 AM
0 8 * * * cd /path/to/oss-radar && .venv/bin/radar daily >> ~/.radar/daily.log 2>&1

# Add weekly digest every Friday at 12 PM
0 12 * * 5 cd /path/to/oss-radar && .venv/bin/radar weekly >> ~/.radar/weekly.log 2>&1
```

---

## Development

```bash
# Run tests
pytest -x

# Run with coverage
pytest --cov=radar --cov-report=html

# Lint
ruff check .

# Format
black .
```
