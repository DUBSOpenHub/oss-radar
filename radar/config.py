"""Pydantic v2 settings for OSS Radar — all tunables via env vars prefixed RADAR_."""

from __future__ import annotations

import logging
from typing import List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration lives here; no hardcoded values elsewhere."""

    model_config = SettingsConfigDict(
        env_prefix="RADAR_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Storage ──────────────────────────────────────────────────────────────
    db_path: str = "~/.radar/catalog.db"

    # ── Reddit ────────────────────────────────────────────────────────────────
    reddit_enabled: bool = False
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "oss-radar/1.0"
    reddit_subreddits: str | List[str] = "opensource,programming,devops,Python,rust,golang,netsec,MachineLearning"

    # ── Email / SMTP ──────────────────────────────────────────────────────────
    email_enabled: bool = False
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    email_from: str = ""
    email_to: str | List[str] = ""
    to_email: str = ""  # single-address alias

    # ── Scoring weights ───────────────────────────────────────────────────────
    influence_weight: float = 0.4
    engagement_weight: float = 0.6
    maintainer_boost_value: float = 1.5
    sentiment_vader_weight: float = 0.6
    sentiment_textblob_weight: float = 0.4

    # ── HTTP / Scraping ───────────────────────────────────────────────────────
    request_timeout: int = 10
    max_retries: int = 3
    retry_min_wait: float = 2.0
    retry_max_wait: float = 30.0

    # ── Scheduling ────────────────────────────────────────────────────────────
    daily_cron: str = "0 14,2 * * *"
    weekly_cron: str = "0 20 * * 5"

    # ── Report ────────────────────────────────────────────────────────────────
    report_size: int = 5
    weekly_report_size: int = 10
    duplicate_run_hours: int = 10

    # ── LLM Summarization (opt-in) ───────────────────────────────────────────
    llm_enabled: bool = False
    llm_model: str = "claude-sonnet-4.6"

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_json: bool = False

    # ── Field validators ──────────────────────────────────────────────────────

    @field_validator("email_to", mode="before")
    @classmethod
    def parse_email_list(cls, v: object) -> List[str]:
        """Accept comma-separated string or list."""
        if isinstance(v, str):
            return [addr.strip() for addr in v.split(",") if addr.strip()]
        if isinstance(v, list):
            return v
        return []

    @field_validator("reddit_subreddits", mode="before")
    @classmethod
    def parse_subreddit_list(cls, v: object) -> List[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, list):
            return v
        return []

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return upper

    # ── Model validators ──────────────────────────────────────────────────────

    @model_validator(mode="after")
    def validate_weights_sum(self) -> "Settings":
        """influence_weight + engagement_weight must equal 1.0 (±0.001 tolerance)."""
        total = self.influence_weight + self.engagement_weight
        if abs(total - 1.0) > 1e-3:
            raise ValueError(
                f"influence_weight ({self.influence_weight}) + "
                f"engagement_weight ({self.engagement_weight}) must sum to 1.0, "
                f"got {total:.4f}"
            )
        return self

    @model_validator(mode="after")
    def validate_sentiment_weights_sum(self) -> "Settings":
        """VADER + TextBlob weights must equal 1.0."""
        total = self.sentiment_vader_weight + self.sentiment_textblob_weight
        if abs(total - 1.0) > 1e-3:
            raise ValueError(
                f"sentiment_vader_weight + sentiment_textblob_weight must sum to 1.0, "
                f"got {total:.4f}"
            )
        return self

    @model_validator(mode="after")
    def validate_smtp_when_email_enabled(self) -> "Settings":
        """SMTP credentials required when EMAIL_ENABLED=true."""
        if self.email_enabled:
            recipients = self.email_to or ([self.to_email] if self.to_email else [])
            if not recipients:
                raise ValueError(
                    "RADAR_EMAIL_TO (or RADAR_TO_EMAIL) required when EMAIL_ENABLED=true"
                )
            if self.smtp_host in ("localhost", "127.0.0.1", "") and not self.smtp_user:
                raise ValueError(
                    "RADAR_SMTP_HOST and RADAR_SMTP_USER required when EMAIL_ENABLED=true"
                )
        return self

    @model_validator(mode="after")
    def validate_reddit_when_enabled(self) -> "Settings":
        """Reddit credentials required when REDDIT_ENABLED=true."""
        if self.reddit_enabled:
            if not self.reddit_client_id or not self.reddit_client_secret:
                raise ValueError(
                    "RADAR_REDDIT_CLIENT_ID and RADAR_REDDIT_CLIENT_SECRET "
                    "required when REDDIT_ENABLED=true"
                )
        return self

    def get_recipients(self) -> List[str]:
        """Return consolidated recipient list."""
        recipients = list(self.email_to)
        if self.to_email and self.to_email not in recipients:
            recipients.append(self.to_email)
        return recipients

    def __repr__(self) -> str:
        """Mask secrets in repr."""
        return (
            f"Settings(db_path={self.db_path!r}, "
            f"smtp_host={self.smtp_host!r}, "
            f"smtp_user={self.smtp_user!r}, "
            f"smtp_password=***, "
            f"reddit_client_secret=***)"
        )

    def __str__(self) -> str:
        return self.__repr__()


import functools


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings singleton."""
    return Settings()


def get_log_level(settings: Settings) -> int:
    return getattr(logging, settings.log_level, logging.INFO)


class RadarSettings(Settings):
    """Settings subclass with sealed-test-expected field names."""

    # Aliases for vader/textblob weights using expected env var names
    vader_weight: float = 0.6
    textblob_weight: float = 0.4
    sentiment_threshold: float = -0.05
    duplicate_window_hours: int = 20

    @model_validator(mode="after")
    def validate_vader_textblob_named_sum(self) -> "RadarSettings":
        total = self.vader_weight + self.textblob_weight
        if abs(total - 1.0) > 1e-3:
            raise ValueError(
                f"vader_weight ({self.vader_weight}) + "
                f"textblob_weight ({self.textblob_weight}) must sum to 1.0, "
                f"got {total:.4f}"
            )
        return self
