# OSS Opportunities Radar — Architecture

## 1. Component Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Entry Points                                                            │
│  ┌──────────────┐  ┌───────────────────────┐  ┌──────────────────────┐  │
│  │  CLI (Typer) │  │ APScheduler (daemon)  │  │ GitHub Actions (cron)│  │
│  └──────┬───────┘  └──────────┬────────────┘  └──────────┬───────────┘  │
└─────────┼────────────────────┼───────────────────────────┼──────────────┘
          └────────────────────▼───────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  pipeline.py        │
                    │  PipelineOrchestrat.│
                    └──────────┬──────────┘
                               │
          ┌────────────────────▼──────────────────────┐
          │              Scraping Layer                │
          │  BaseScraper (ABC)  +  SafeHTTPClient      │
          │  ┌──────────┬──────────┬─────────────────┐ │
          │  │ Reddit   │    HN    │ Dev.to  Lobsters │ │
          │  └──────────┴──────────┴─────────────────┘ │
          └────────────────────┬──────────────────────┘
                               │ List[RawPost]
          ┌────────────────────▼──────────────────────┐
          │              Ranking Layer                 │
          │  ┌────────────────────────────────────┐    │
          │  │ 1. KeywordFilter                   │    │
          │  │    100+ compiled regex patterns    │    │
          │  │    15 PainCategory enums           │    │
          │  └─────────────────┬──────────────────┘    │
          │                    │                       │
          │  ┌─────────────────▼──────────────────┐    │
          │  │ 2. MaintainerContextFilter         │    │
          │  │    10+ role/context patterns       │    │
          │  └─────────────────┬──────────────────┘    │
          │                    │                       │
          │  ┌─────────────────▼──────────────────┐    │
          │  │ 3. SentimentFilter                 │    │
          │  │    VADER(0.6) + TextBlob(0.4)      │    │
          │  └─────────────────┬──────────────────┘    │
          │                    │                       │
          │  ┌─────────────────▼──────────────────┐    │
          │  │ SignalScorer                        │    │
          │  │    batch-normalized scoring        │    │
          │  └─────────────────┬──────────────────┘    │
          └────────────────────┼──────────────────────┘
                               │ List[ScoredPost]
          ┌────────────────────▼──────────────────────┐
          │           BackfillManager                  │
          │   live → archive-7d → archive-30d → partial│
          └────────────────────┬──────────────────────┘
                               │ DailyReport | WeeklyReport
          ┌────────────────────▼──────────────────────┐
          │          Storage Layer                     │
          │  SQLite (WAL) — 3 tables, SHA-256 dedup   │
          └────────────────────┬──────────────────────┘
                               │
          ┌────────────────────▼──────────────────────┐
          │           Email Layer                      │
          │  Jinja2 templates → multipart MIME → SMTP │
          └───────────────────────────────────────────┘
```

---

## 2. Module Descriptions

| Module | File | Responsibility |
|---|---|---|
| CLI | `radar/cli.py` | Typer app; commands `run`, `daemon`, `digest`; exit codes 0/1/2 |
| Config | `radar/config.py` | Pydantic v2 Settings; env loading; conditional validation |
| Models | `radar/models.py` | All Pydantic models and enums |
| Pipeline | `radar/pipeline.py` | Orchestrates scrape→filter→rank→backfill→store→email |
| Keywords | `radar/ranking/keywords.py` | PainCategory enum; compiled regex registry |
| Filters | `radar/ranking/filters.py` | Three filter classes |
| Scorer | `radar/ranking/scorer.py` | Batch normalization; signal score formula |
| HTTP | `radar/scraping/http.py` | SSRF-safe httpx client with tenacity retries |
| BaseScraper | `radar/scraping/base.py` | Abstract base class |
| Scrapers | `radar/scraping/{reddit,hackernews,devto,lobsters}.py` | Platform implementations |
| Database | `radar/storage/database.py` | SQLite WAL; CRUD; dedup; migrations |
| Sender | `radar/email/sender.py` | Jinja2 render; SMTP send; multipart MIME |
| Templates | `radar/email/templates/` | `daily.html.j2`, `weekly.html.j2` |
| Scheduler | `radar/scheduling/scheduler.py` | APScheduler daemon wrapper |

---

## 3. Data Flow

```
scrape()        → List[RawPost]           (per scraper, independent)
keyword_filter()→ List[RawPost]           (drops non-pain posts)
context_filter()→ List[RawPost]           (keeps maintainer-authored)
sentiment_filter()→ List[RawPost]         (removes positive/neutral)
score_batch()   → List[ScoredPost]        (batch-normalized scores)
backfill()      → List[ScoredPost]        (exactly 5, fallback ladder)
store_run()     → run_id: int             (persists to SQLite)
build_report()  → DailyReport             (top 5 + metadata)
render()        → str (HTML)              (Jinja2 template)
send_email()    → None                    (SMTP dispatch)
```

Each scraper runs inside a try/except; failures are logged and the
platform is skipped. The pipeline continues with results from surviving
scrapers (graceful degradation).

---

## 4. Key Interfaces

### 4.1 BaseScraper ABC (`radar/scraping/base.py`)

```python
class BaseScraper(ABC):
    platform: str                          # class-level constant
    def __init__(self, config: Settings, client: SafeHTTPClient) -> None: ...

    @abstractmethod
    def fetch_raw(self) -> List[RawPost]: ...

    def scrape(self) -> List[RawPost]:
        """Public entry point. Wraps fetch_raw with logging + error isolation."""

    def _build_post(self, raw: dict) -> RawPost: ...
    def _dedup_key(self, url: str) -> str: ...   # SHA-256 hex of url
```

### 4.2 Filter Pipeline (`radar/ranking/filters.py`)

```python
class KeywordFilter:
    def __init__(self, patterns: Dict[PainCategory, List[re.Pattern]]) -> None: ...
    def apply(self, posts: List[RawPost]) -> List[RawPost]: ...
    def _score_categories(self, text: str) -> Dict[PainCategory, int]: ...

class MaintainerContextFilter:
    def __init__(self, patterns: List[re.Pattern]) -> None: ...
    def apply(self, posts: List[RawPost]) -> List[RawPost]: ...
    def _is_maintainer(self, post: RawPost) -> bool: ...

class SentimentFilter:
    def __init__(self, vader_weight: float = 0.6, textblob_weight: float = 0.4) -> None: ...
    def apply(self, posts: List[RawPost]) -> List[RawPost]: ...
    def _combined_score(self, text: str) -> float: ...  # negative = pain
```

### 4.3 Scorer (`radar/ranking/scorer.py`)

```python
class SignalScorer:
    def score_batch(self, posts: List[RawPost]) -> List[ScoredPost]: ...
    def _normalize(self, values: List[float]) -> List[float]: ...  # min-max
    def _signal_score(
        self,
        influence_norm: float,   # weight 0.4
        engagement_norm: float,  # weight 0.6
        pain_factor: float,      # 1.0–2.0 per PainCategory
        sentiment_factor: float, # 0.5–1.5 from combined sentiment
        maintainer_boost: float, # 1.0 or 1.5
    ) -> float: ...
    # Formula: (influence_norm*0.4 + engagement_norm*0.6)
    #          * pain_factor * sentiment_factor * maintainer_boost
```

### 4.4 Pipeline (`radar/pipeline.py`)

```python
class PipelineOrchestrator:
    def __init__(self, config: Settings, db: Database) -> None: ...
    def run_daily(self) -> DailyReport: ...
    def run_weekly(self) -> WeeklyReport: ...
    def _collect(self) -> List[RawPost]: ...
    def _filter(self, posts: List[RawPost]) -> List[RawPost]: ...
    def _rank(self, posts: List[RawPost]) -> List[ScoredPost]: ...
    def _backfill(self, posts: List[ScoredPost]) -> List[ScoredPost]: ...
```

### 4.5 BackfillManager (`radar/pipeline.py` or inline)

```python
class BackfillManager:
    LADDER = ["live", "archive_7d", "archive_30d", "partial"]
    def __init__(self, db: Database) -> None: ...
    def ensure_five(self, posts: List[ScoredPost]) -> List[ScoredPost]: ...
    def _from_archive(self, days: int, needed: int) -> List[ScoredPost]: ...
```

---

## 5. Pydantic Models (`radar/models.py`)

```python
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, HttpUrl, Field

class PainCategory(str, Enum):
    DEPENDENCY_HELL   = "dependency_hell"
    BREAKING_CHANGES  = "breaking_changes"
    CI_CD_FAILURES    = "ci_cd_failures"
    SECURITY_VULNS    = "security_vulns"
    DOCS_GAPS         = "docs_gaps"
    CONTRIBUTOR_CHURN = "contributor_churn"
    PERFORMANCE       = "performance"
    PACKAGING         = "packaging"
    LICENSING         = "licensing"
    API_DESIGN        = "api_design"
    TESTING           = "testing"
    RELEASE_MGMT      = "release_mgmt"
    COMMUNITY         = "community"
    FUNDING           = "funding"
    TOOLING           = "tooling"

class RawPost(BaseModel):
    id: str                              # SHA-256 of url
    platform: str
    title: str
    body: str
    url: HttpUrl
    author: str
    score: int                           # platform upvotes/karma
    comment_count: int
    created_utc: datetime
    pain_categories: List[PainCategory] = Field(default_factory=list)
    is_maintainer_context: bool = False
    raw_sentiment: float = 0.0           # combined VADER+TextBlob

class ScoredPost(RawPost):
    influence_norm: float
    engagement_norm: float
    pain_factor: float
    sentiment_factor: float
    maintainer_boost: float
    signal_score: float
    backfill_source: str = "live"        # "live"|"archive_7d"|"archive_30d"|"partial"

class DailyReport(BaseModel):
    run_id: int
    generated_at: datetime
    top_posts: List[ScoredPost]          # exactly 5
    scraper_statuses: Dict[str, str]     # platform → "ok"|"failed"|"empty"
    total_collected: int
    total_after_filter: int

class WeeklyReport(BaseModel):
    week_start: datetime
    week_end: datetime
    generated_at: datetime
    top_posts: List[ScoredPost]          # top 5 from the week
    platform_breakdown: Dict[str, int]
    category_breakdown: Dict[PainCategory, int]
    run_count: int
```

---

## 6. Database Design (`radar/storage/database.py`)

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type    TEXT    NOT NULL CHECK (run_type IN ('daily','weekly')),
    started_at  TEXT    NOT NULL,   -- ISO-8601 UTC
    finished_at TEXT,
    status      TEXT    NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running','success','failed')),
    post_count  INTEGER DEFAULT 0,
    meta        TEXT                -- JSON blob (scraper_statuses, etc.)
);

CREATE TABLE IF NOT EXISTS posts (
    id                   TEXT    PRIMARY KEY,   -- SHA-256(url)
    run_id               INTEGER NOT NULL REFERENCES runs(id),
    platform             TEXT    NOT NULL,
    title                TEXT    NOT NULL,
    body                 TEXT,
    url                  TEXT    NOT NULL UNIQUE,
    author               TEXT,
    platform_score       INTEGER DEFAULT 0,
    comment_count        INTEGER DEFAULT 0,
    created_utc          TEXT    NOT NULL,
    pain_categories      TEXT,   -- JSON array of PainCategory values
    is_maintainer        INTEGER DEFAULT 0,
    raw_sentiment        REAL    DEFAULT 0.0,
    signal_score         REAL    DEFAULT 0.0,
    influence_norm       REAL    DEFAULT 0.0,
    engagement_norm      REAL    DEFAULT 0.0,
    pain_factor          REAL    DEFAULT 1.0,
    sentiment_factor     REAL    DEFAULT 1.0,
    maintainer_boost     REAL    DEFAULT 1.0,
    backfill_source      TEXT    DEFAULT 'live',
    archived_at          TEXT    NOT NULL        -- ISO-8601 UTC, set on insert
);

CREATE TABLE IF NOT EXISTS email_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    email_type  TEXT    NOT NULL CHECK (email_type IN ('daily','weekly')),
    recipient   TEXT    NOT NULL,
    sent_at     TEXT    NOT NULL,
    status      TEXT    NOT NULL CHECK (status IN ('sent','failed')),
    error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_posts_run_id    ON posts(run_id);
CREATE INDEX IF NOT EXISTS idx_posts_archived  ON posts(archived_at);
CREATE INDEX IF NOT EXISTS idx_posts_score     ON posts(signal_score DESC);
```

**Key database methods:**

```python
class Database:
    def __init__(self, path: str) -> None: ...
    def upsert_post(self, post: ScoredPost, run_id: int) -> None: ...
    def fetch_archive(self, days: int, limit: int) -> List[ScoredPost]: ...
    def start_run(self, run_type: str) -> int: ...                     # returns run_id
    def finish_run(self, run_id: int, status: str, count: int) -> None: ...
    def log_email(self, run_id: int, email_type: str, recipient: str, status: str, error: str = None) -> None: ...
    def get_weekly_posts(self, week_start: datetime, week_end: datetime) -> List[ScoredPost]: ...
```

---

## 7. Configuration Architecture (`radar/config.py`)

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Scraping
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "oss-radar/1.0"
    reddit_subreddits: List[str] = ["opensource", "programming", "devops"]

    # Storage
    db_path: str = "radar.db"

    # Email
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    email_from: str = ""
    email_to: List[str] = []

    # Scoring weights (immutable at runtime)
    influence_weight: float = 0.4
    engagement_weight: float = 0.6
    maintainer_boost_value: float = 1.5

    # Scheduling
    daily_cron: str = "0 16 * * *"
    weekly_cron: str = "0 20 * * 5"

    # HTTP safety
    allowed_hosts: List[str] = ["reddit.com", "hacker-news.firebaseio.com",
                                  "dev.to", "lobste.rs"]
    request_timeout: int = 15
    max_retries: int = 3

    @field_validator("email_to", mode="before")
    @classmethod
    def parse_email_list(cls, v): ...   # split comma-string or accept list

    @model_validator(mode="after")
    def validate_smtp_when_sending(self) -> "Settings": ...
    # Raises if email_to non-empty but smtp_host is "localhost" and no credentials
```

**Secret redaction**: `Settings.__repr__` and `__str__` mask `smtp_password`,
`reddit_client_secret` with `***`. structlog processor does the same for log lines.

---

## 8. Error Handling Strategy

### Tenacity Retry Policy (`radar/scraping/http.py`)

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    reraise=False,
)
def get(self, url: str, **kwargs) -> httpx.Response: ...
```

### Graceful Degradation

Each scraper is called inside `PipelineOrchestrator._collect()`:

```python
for scraper in self.scrapers:
    try:
        posts.extend(scraper.scrape())
        statuses[scraper.platform] = "ok"
    except Exception as e:
        statuses[scraper.platform] = "failed"
        log.error("scraper_failed", platform=scraper.platform, error=str(e))
```

Pipeline continues with results from surviving scrapers.

### Exit Codes (`radar/cli.py`)

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Partial failure (some scrapers failed, report still delivered) |
| 2 | Fatal failure (all scrapers failed or email send failed) |

### SSRF Protection (`radar/scraping/http.py`)

```python
class SafeHTTPClient:
    def __init__(self, allowed_hosts: List[str], timeout: int) -> None: ...
    def _assert_allowed(self, url: str) -> None:
        """Raises ValueError if netloc not in allowed_hosts."""
    def get(self, url: str, **kwargs) -> httpx.Response: ...
    def post(self, url: str, **kwargs) -> httpx.Response: ...
```

Private/loopback IPs are also blocked via a DNS pre-check using `socket.getaddrinfo`.

---

## 9. Email Architecture

### Sender (`radar/email/sender.py`)

```python
class EmailSender:
    def __init__(self, config: Settings) -> None: ...

    def send_daily(self, report: DailyReport) -> None:
        html = self._render("daily.html.j2", {"report": report})
        self._send(subject=f"OSS Radar — {report.generated_at.date()}", html=html)

    def send_weekly(self, report: WeeklyReport) -> None:
        html = self._render("weekly.html.j2", {"report": report})
        self._send(subject=f"OSS Radar Weekly — {report.week_start.date()}", html=html)

    def _render(self, template_name: str, context: dict) -> str:
        """Loads Jinja2 template from radar/email/templates/, returns HTML string."""

    def _send(self, subject: str, html: str) -> None:
        """Builds multipart/alternative MIME (text/plain + text/html), sends via SMTP."""

    def _build_mime(self, subject: str, html: str) -> MIMEMultipart: ...
    def _plaintext_fallback(self, html: str) -> str: ...   # strip tags
```

### Template Contract

Both templates receive the full report model serialized as a dict.
Dark-mode CSS uses `@media (prefers-color-scheme: dark)` with inline fallback
(`background:#0d1117; color:#e6edf3`). Templates are Jinja2 `Environment`
with `autoescape=True` and `undefined=StrictUndefined`.

---

## 10. Security Considerations

| Risk | Mitigation |
|---|---|
| SSRF via scraper URLs | `SafeHTTPClient._assert_allowed()` allowlist + private IP block |
| Secret leakage in logs | structlog `redact_processor` masks `*password*`, `*secret*`, `*token*` keys |
| Secret leakage in repr | `Settings.__repr__` custom override |
| SQLite injection | All DB access via parameterised queries (`?` placeholders) |
| XSS in email templates | Jinja2 `autoescape=True` on all templates |
| Credential storage | Loaded exclusively from env / `.env` file; never hardcoded |
| `.env` in VCS | `.gitignore` includes `.env`; `.env.example` ships with placeholders |

---

## 11. File-by-File Responsibility Map

```
radar/cli.py
  - Typer app with commands: run (daily), digest (weekly), daemon
  - Maps PipelineOrchestrator return to exit codes 0/1/2
  - Rich console output: progress bars, summary table

radar/config.py
  - Settings(BaseSettings): all env vars, field validators, model validators
  - get_settings() → cached singleton via functools.lru_cache

radar/models.py
  - PainCategory(str, Enum): 15 values
  - RawPost, ScoredPost, DailyReport, WeeklyReport Pydantic models

radar/pipeline.py
  - PipelineOrchestrator: run_daily(), run_weekly()
  - BackfillManager: ensure_five() with 4-rung fallback ladder

radar/ranking/keywords.py
  - PAIN_PATTERNS: Dict[PainCategory, List[str]] — raw pattern strings
  - COMPILED_PATTERNS: Dict[PainCategory, List[re.Pattern]] — module-level compiled
  - PAIN_FACTORS: Dict[PainCategory, float] — per-category score multipliers
  - MAINTAINER_PATTERNS: List[re.Pattern]

radar/ranking/filters.py
  - KeywordFilter, MaintainerContextFilter, SentimentFilter
  - FilterPipeline: composes all three, apply(posts) → posts

radar/ranking/scorer.py
  - SignalScorer: score_batch(), _normalize(), _signal_score()

radar/scraping/http.py
  - SafeHTTPClient: get(), post(), _assert_allowed(), _block_private_ip()

radar/scraping/base.py
  - BaseScraper(ABC): scrape(), fetch_raw(), _build_post(), _dedup_key()

radar/scraping/reddit.py
  - RedditScraper(BaseScraper): uses praw; fetches top N posts from subreddits

radar/scraping/hackernews.py
  - HNScraper(BaseScraper): hits Algolia HN Search API via SafeHTTPClient

radar/scraping/devto.py
  - DevToScraper(BaseScraper): Dev.to public REST API; tag-filtered

radar/scraping/lobsters.py
  - LobstersScraper(BaseScraper): Lobsters JSON API; newest/hottest endpoints

radar/storage/database.py
  - Database: __init__(path), upsert_post(), fetch_archive(), start_run(),
    finish_run(), log_email(), get_weekly_posts()
  - _migrate(): runs CREATE TABLE IF NOT EXISTS on first connection

radar/email/sender.py
  - EmailSender: send_daily(), send_weekly(), _render(), _send(), _build_mime()

radar/email/templates/daily.html.j2
  - Dark-mode HTML; renders top_posts list with title, url, platform badge,
    signal_score, pain_categories chips, author context snippet

radar/email/templates/weekly.html.j2
  - Dark-mode HTML; same post list plus platform_breakdown bar chart (CSS-only)
    and category_breakdown table

radar/scheduling/scheduler.py
  - RadarScheduler: start(), stop()
  - Registers daily job (run_daily) and weekly job (run_weekly) with APScheduler
    BlockingScheduler; reads cron strings from Settings

tests/conftest.py
  - Fixtures: tmp_db, mock_settings, sample_raw_posts, sample_scored_posts

tests/test_config.py      — Settings validation, env var loading, secret redaction
tests/test_ranking.py     — KeywordFilter, MaintainerContextFilter, SentimentFilter,
                            SignalScorer, FilterPipeline (unit + property tests)
tests/test_scraping.py    — Each scraper with httpx mock; BaseScraper contract
tests/test_storage.py     — Database CRUD, dedup, fetch_archive, weekly query
tests/test_email.py       — Template rendering, MIME structure, SMTP mock
tests/test_pipeline.py    — PipelineOrchestrator end-to-end with mocked scrapers;
                            backfill ladder; exit-code mapping
```

---

*Architecture version: 1.0 — aligns with PRD v1. Implementation must not deviate
from directory structure, model fields, or interface signatures defined here.*
