# Agents

## Overview

OSS Radar is an autonomous Python pipeline agent — not a Copilot CLI agent file, but a self-contained daemon that acts as an intelligent agent for monitoring open source developer pain points. It autonomously scrapes four developer platforms (Hacker News, Dev.to, Lobsters, Reddit), applies multi-layer filtering and scoring, optionally summarizes via LLM, and delivers ranked intelligence by email with zero ongoing interaction required.

## Available Agents

### OSS Radar Pipeline (Autonomous Daemon)

- **Purpose**: Monitors Hacker News, Dev.to, Lobsters, and Reddit for genuine open source maintainer pain points. Filters noise with 100+ keyword patterns, maintainer context detection, and sentiment analysis (VADER + TextBlob). Ranks posts by signal strength. Delivers a daily email with the 5 highest-signal pain points and a weekly Friday digest of trends.
- **Usage**:
  ```bash
  # Local daemon (macOS) — runs automatically via launchd
  bash install.sh
  # Edit .env with SMTP credentials, then it runs on its own

  # GitHub Actions (cloud, zero infrastructure)
  # Add secrets: RADAR_SMTP_HOST, RADAR_SMTP_PORT, RADAR_SMTP_USER,
  #              RADAR_SMTP_PASSWORD, RADAR_EMAIL_FROM, RADAR_EMAIL_TO
  # Scrapes hourly; daily email at 6 AM PST; weekly digest Fridays at 12 PM PST

  # Manual CLI run
  python -m radar run        # Single pipeline pass
  python -m radar status     # Check daemon health
  python -m radar backfill   # Fill historical gaps
  ```
- **Model**: GitHub Models API (opt-in LLM summarization); falls back to Amplifier CLI if configured
- **Schedule**: Daily scrape runs 2× per day; weekly trend digest every Friday

### LLM Summarizer (Optional Sub-Agent)

- **Purpose**: Summarizes and contextualizes top-ranked pain points using an LLM. Opt-in component within the pipeline.
- **Usage**: Set `RADAR_LLM_ENABLED=true` in `.env` or GitHub Actions secrets. Uses GitHub Models API by default; falls back to Amplifier CLI.
- **Model**: Configurable via `RADAR_LLM_MODEL` environment variable

## Configuration

- All configuration via `.env` file (local) or GitHub Actions secrets (cloud)
- Required: `RADAR_SMTP_HOST`, `RADAR_SMTP_PORT`, `RADAR_SMTP_USER`, `RADAR_SMTP_PASSWORD`, `RADAR_EMAIL_FROM`, `RADAR_EMAIL_TO`
- Optional: `RADAR_REDDIT_CLIENT_ID`, `RADAR_REDDIT_CLIENT_SECRET` (for higher Reddit API rate limits)
- Optional: `RADAR_LLM_ENABLED=true`, `RADAR_LLM_MODEL` (for AI-generated summaries)
- State is stored in a local SQLite database (WAL mode, 3 tables) for deduplication and trend tracking
- Backfill ladder: live → 7-day archive → 30-day archive → partial data if all sources unavailable

## Using GitHub Copilot with This Repo

Copilot can assist with:
- Extending the scraper to new platforms (add a new source module in `scrapers/`)
- Tuning the keyword filter patterns in `filters/keyword_filter.py`
- Adjusting the signal scoring formula in `ranking/signal_scorer.py`
- Customizing the email template (Jinja2 in `templates/`)
- Writing tests for pipeline stages
