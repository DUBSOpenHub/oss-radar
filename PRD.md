# PRD: OSS Opportunities Radar

## Overview / Product Vision

A production-ready Python daemon that monitors four developer platforms daily, extracts genuine open source maintainer pain points, ranks them by signal strength, persists them in a local catalog, and delivers curated intelligence via email — requiring zero interaction after initial setup.

---

## User Stories

- **US-1** As an operator, I run `radar schedule` once and receive daily + weekly reports indefinitely without further action.
- **US-2** As an operator, I receive exactly 5 ranked pain points per daily report, or a labeled partial list when fewer are found.
- **US-3** As an operator, I receive a weekly Friday digest of the top 10 unique findings from the prior 7 days.
- **US-4** As an operator, I run `radar stats` at any time to see catalog size, last-run timestamp, and report counts.
- **US-5** As an operator, I run `radar validate` and immediately know whether credentials and connectivity are healthy.
- **US-6** As an operator, I trust every reported item was authored by someone with genuine maintainer context.

---

## Functional Requirements

### FR-1 — Multi-Platform Scraping
- **FR-1.1** Reddit via PRAW: `r/opensource`, `r/programming`, `r/devops`, `r/Python`, `r/rust`, `r/golang`, `r/netsec`, `r/MachineLearning`.
- **FR-1.2** Hacker News via Algolia (`hn.algolia.com/api/v1/search`), tags `ask_hn` and `show_hn`.
- **FR-1.3** Dev.to via public REST (`dev.to/api/articles`), tags `opensource`, `devops`, `python`, `github`.
- **FR-1.4** Lobsters via JSON feeds: `lobste.rs/t/programming.json`, `lobste.rs/t/security.json`.
- **FR-1.5** Each scraper runs independently; its failure must not propagate to other scrapers.
- **FR-1.6** All HTTP requests: 10-second timeout, `tenacity` retries: 3 attempts, exponential backoff from 2 seconds.
- **FR-1.7** SSRF protection: block RFC-1918 + loopback (`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).

### FR-2 — Multi-Layer Signal Filtering
- **FR-2.1** **Layer 1 — Keyword Gate**: title + body must match ≥1 keyword across 15 `PainCategory` enums: `DEPENDENCY_HELL`, `CI_CD_FAILURES`, `SECURITY_VULNS`, `BURNOUT`, `FUNDING_SUSTAINABILITY`, `DOCUMENTATION_DEBT`, `BREAKING_CHANGES`, `COMMUNITY_TOXICITY`, `INFRASTRUCTURE_COST`, `LICENSE_ISSUES`, `CONTRIBUTION_FRICTION`, `RELEASE_AUTOMATION`, `TEST_FLAKINESS`, `API_INSTABILITY`, `GOVERNANCE`. Total keyword list ≥100 terms.
- **FR-2.2** **Layer 2 — Maintainer Context**: post must contain ≥1 of: `my repo`, `my project`, `I maintain`, `we maintain`, `our library`, `I'm the author`, `I released`, `our maintainers`, `pull request`, `merged`, `opened an issue`, `released v`, or author username in a GitHub URL within the post.
- **FR-2.3** **Layer 3 — Dual Sentiment**: `sentiment_score = (VADER_compound × 0.6) + (TextBlob_polarity × 0.4)`. Post must have `sentiment_score < −0.05` to pass.
- **FR-2.4** All three layers must pass; failure at any layer silently discards the post.

### FR-3 — Signal Ranking Algorithm
- **FR-3.1** `influence_norm = log10(author_karma + 1) / log10(max_karma_in_batch + 1)`, clamped `[0.0, 1.0]`.
- **FR-3.2** `engagement_norm = log10(score + comments + 1) / log10(max_engagement_in_batch + 1)`, clamped `[0.0, 1.0]`.
- **FR-3.3** `pain_factor`: 1 keyword match = 1.0; 2–3 matches = 1.2; 4+ matches = 1.5.
- **FR-3.4** `maintainer_boost`: 1 context signal = 1.0; 2+ signals = 1.25.
- **FR-3.5** `signal_score = (influence_norm × 0.4 + engagement_norm × 0.6) × pain_factor × (1.0 + abs(sentiment_score)) × maintainer_boost`.
- **FR-3.6** Posts ranked descending by `signal_score` within a daily batch.

### FR-4 — Exactly-5 Fallback Ladder
- **FR-4.1** Four rungs attempted in order until 5 posts are found: (1) **live** — past 24h; (2) **archive-7d** — past 7 days, not previously reported; (3) **archive-30d** — past 30 days, not previously reported; (4) **partial** — all available qualifying posts.
- **FR-4.2** Each rung is attempted only if the prior rung yields fewer than 5 posts.
- **FR-4.3** Each report item carries a `source_tier` label: `live`, `archive-7d`, `archive-30d`, or `partial`.
- **FR-4.4** A partial report (fewer than 5 items) exits with code `1`.

### FR-5 — Persistent Catalog (SQLite)
- **FR-5.1** DB path: `~/.radar/catalog.db`; WAL journal mode enabled on every connection.
- **FR-5.2** Table `posts`: `id INTEGER PK`, `url_hash TEXT UNIQUE` (SHA-256 of normalized URL), `url TEXT`, `title TEXT`, `body TEXT`, `author TEXT`, `platform TEXT`, `score INTEGER`, `comments INTEGER`, `author_karma INTEGER`, `signal_score REAL`, `pain_categories TEXT` (JSON array), `source_tier TEXT`, `fetched_at TEXT` (ISO-8601), `reported_at TEXT` (nullable ISO-8601).
- **FR-5.3** Table `reports`: `id INTEGER PK`, `report_type TEXT` (`daily`|`weekly`), `generated_at TEXT`, `recipient TEXT`, `status TEXT` (`sent`|`failed`).
- **FR-5.4** Table `report_entries`: `report_id INTEGER FK`, `post_id INTEGER FK`, `rank INTEGER`.
- **FR-5.5** A post whose `url_hash` already exists in `posts` is silently skipped on re-ingestion.
- **FR-5.6** Duplicate-run guard: if a `daily` report with `status = sent` exists with `generated_at` within the prior 20 hours, exit `0` with log `"duplicate run skipped"` unless `--force` is passed.

### FR-6 — Daily Email Report
- **FR-6.1** Subject: `[OSS Radar] Daily Intel — {YYYY-MM-DD}`.
- **FR-6.2** Body: dark-mode HTML rendered from a Jinja2 template file (not inline f-strings); multipart MIME with plain-text fallback.
- **FR-6.3** Each entry shows: rank, linked title, platform badge, `source_tier`, top 3 `pain_categories`, `signal_score` (2 dp), ≤120-char body excerpt.
- **FR-6.4** SMTP with STARTTLS; credentials from env vars `RADAR_SMTP_HOST`, `RADAR_SMTP_PORT`, `RADAR_SMTP_USER`, `RADAR_SMTP_PASSWORD`, `RADAR_TO_EMAIL`.
- **FR-6.5** SMTP failure: retry once after 60 seconds; on second failure write `status = failed` to `reports` and exit `1`.

### FR-7 — Weekly Digest
- **FR-7.1** Triggered every Friday; cron `0 20 * * 5` (UTC).
- **FR-7.2** Subject: `[OSS Radar] Weekly Digest — Week of {YYYY-MM-DD}`.
- **FR-7.3** Top 10 unique posts by `signal_score` from `report_entries` ⋈ `posts` where `reported_at` falls within the prior 7 days; deduped by `url_hash`.
- **FR-7.4** Layout identical to FR-6.2/FR-6.3 plus a "week" header banner.

### FR-8 — CLI Interface
- **FR-8.1** Built with Typer; all output uses Rich (tables, progress bars, colored status).
- **FR-8.2** Commands: `radar scrape`, `radar daily`, `radar weekly`, `radar validate`, `radar schedule`, `radar report [--id ID]`, `radar stats`.
- **FR-8.3** `radar validate`: live HTTP probe + SMTP check + DB write check; Rich table with pass/fail per check; exit `0` if all pass, `1` otherwise.
- **FR-8.4** `radar stats`: catalog row count, last-run timestamp, count of `sent` daily and weekly reports.
- **FR-8.5** `radar schedule`: writes cron entries to user crontab without duplicating existing entries.
- **FR-8.6** All commands accept `--force` (bypass duplicate guard) and `--dry-run` (skip SMTP send and DB writes).

### FR-9 — GitHub Actions Automation
- **FR-9.1** `.github/workflows/daily.yml`: cron `0 16 * * *` (UTC), runs `radar daily`.
- **FR-9.2** `.github/workflows/weekly.yml`: cron `0 20 * * 5` (UTC), runs `radar weekly`.
- **FR-9.3** Both workflows: checkout, Python 3.11 setup, `pip install -r requirements.txt`, secrets injected as env vars per FR-6.4, upload `~/.radar/catalog.db` as artifact on failure.

---

## Non-Functional Requirements

- **NFR-1 Config**: All tuneable values via Pydantic v2 `BaseSettings`; env vars prefixed `RADAR_`. No hardcoded secrets.
- **NFR-2 Security**: SSRF per FR-1.7. SMTP credentials never logged. DB file created with permissions `0600`.
- **NFR-3 Exit Codes**: `0` = full success; `1` = partial (< 5 items or SMTP retry exhausted); `2` = total failure (DB unwritable, all scrapers failed, unhandled exception).
- **NFR-4 Observability**: `structlog` throughout; JSON format when `CI=true`, human-readable otherwise. Each scraper logs: items fetched, items passing each filter layer, items after dedup.
- **NFR-5 Code Quality**: Type hints on all public functions/attributes. No untyped `Any`. `pyproject.toml` with `ruff` and `black` config.
- **NFR-6 Tests**: ≥40 `pytest` cases; all pass via `pytest -x` with no network calls and no env vars set (mock all externals). Coverage: each scraper, each filter layer, ranking formula, fallback ladder, DB dedup, email template rendering, CLI via `CliRunner`, exit codes.
- **NFR-7 Docs**: `README.md` with 3-command quickstart, env var reference table, CLI reference, cron schedule explanation. Docstrings on all public modules, classes, and functions.

---

## Acceptance Criteria

1. `radar validate` exits `0` with all checks passing when valid credentials are configured.
2. `radar daily` inserts exactly 5 rows into `report_entries` when ≥5 qualifying posts are found.
3. `radar daily` inserts fewer than 5 rows and exits `1` when the 30-day archive yields fewer than 5 qualifying posts.
4. A post with a duplicate `url_hash` is not re-inserted into `posts` on a second scrape.
5. `radar daily` exits `0` (skipped) within 20 hours of a prior successful daily report, absent `--force`.
6. `radar daily --force` overrides the 20-hour guard and runs to completion.
7. `radar daily --dry-run` performs all scraping and filtering but writes nothing to the DB and sends no email.
8. Daily email subject exactly matches `[OSS Radar] Daily Intel — {YYYY-MM-DD}`.
9. Weekly email subject exactly matches `[OSS Radar] Weekly Digest — Week of {YYYY-MM-DD}`.
10. Every report item includes a `source_tier` label from `{live, archive-7d, archive-30d, partial}`.
11. A post with `sentiment_score ≥ −0.05` is never included in any report.
12. A post containing zero maintainer-context signals (FR-2.2) is never included in any report.
13. `pytest -x` passes all ≥40 tests with no network access and no env vars set.
14. Both GitHub Actions workflow files exist with correct cron schedules and CI passes on a clean checkout.

---

## Out of Scope

No AI/LLM summarization. No web dashboard, UI, or REST API. No paid APIs. No Twitter/X, LinkedIn, Mastodon, or Stack Overflow. No Slack/Discord/webhook integrations. No multi-user support. No streaming or real-time scraping. No containerization.

---

## Architecture Constraints (Directory Structure)

```
oss-radar/
├── pyproject.toml
├── requirements.txt
├── README.md
├── .github/workflows/{daily,weekly}.yml
├── radar/
│   ├── cli.py          scraper/reddit.py     templates/daily.html.j2
│   ├── config.py       scraper/hackernews.py templates/weekly.html.j2
│   ├── db.py           scraper/devto.py
│   ├── filter.py       scraper/lobsters.py
│   ├── scorer.py       mailer.py
│   └── ladder.py
└── tests/
    ├── conftest.py  test_filter.py  test_db.py   test_cli.py
    ├── test_scrapers.py  test_scorer.py  test_mailer.py  test_ladder.py
```

---

## Dependencies

`praw` · `httpx` · `tenacity` · `vaderSentiment` · `textblob` · `pydantic[email]>=2.0` · `structlog` · `typer[all]` · `rich` · `jinja2` · `pytest` · `pytest-cov` · `ruff` · `black`
