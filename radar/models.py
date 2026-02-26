"""Pydantic models and enums for OSS Radar."""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class PainCategory(str, Enum):
    """15 pain categories tracked by the OSS Radar."""

    BURNOUT = "burnout"
    FUNDING = "funding"
    TOXIC_USERS = "toxic_users"
    MAINTENANCE_BURDEN = "maintenance_burden"
    DEPENDENCY_HELL = "dependency_hell"
    SECURITY_PRESSURE = "security_pressure"
    BREAKING_CHANGES = "breaking_changes"
    DOCUMENTATION = "documentation"
    CONTRIBUTOR_FRICTION = "contributor_friction"
    CORPORATE_EXPLOITATION = "corporate_exploitation"
    SCOPE_CREEP = "scope_creep"
    TOOLING_FATIGUE = "tooling_fatigue"
    GOVERNANCE = "governance"
    ABUSE = "abuse"
    CI_CD = "ci_cd"


def _sha256_url(url: str) -> str:
    """Return SHA-256 hex digest of a normalised URL string."""
    normalised = url.strip().lower().rstrip("/")
    return hashlib.sha256(normalised.encode()).hexdigest()


class RawPost(BaseModel):
    """A raw post fetched from any platform, before scoring."""

    url: str
    url_hash: str = ""
    title: str
    body: str = ""
    platform: str
    author: str = ""
    # Influence signal — Reddit karma, HN points, etc.
    followers: int = 0
    author_karma: int = 0  # alias for followers/karma
    # Engagement signals
    upvotes: int = 0
    score: int = 0  # alias for upvotes
    comments: int = 0
    comment_count: int = 0  # alias for comments
    tags: List[str] = Field(default_factory=list)
    pain_categories: List[PainCategory] = Field(default_factory=list)
    pain_score: float = 0.0
    sentiment: float = 0.0
    raw_sentiment: float = 0.0  # alias for sentiment
    is_maintainer: bool = False
    is_maintainer_context: bool = False  # alias
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    created_utc: Optional[datetime] = None
    # Fallback ladder provenance
    source_tier: str = "live"
    backfill_source: str = "live"

    @field_validator("url_hash", mode="before")
    @classmethod
    def compute_url_hash(cls, v: str, info: object) -> str:
        if v:
            return v
        # Access url from field data via info.data
        try:
            url = info.data.get("url", "")  # type: ignore[union-attr]
        except AttributeError:
            url = ""
        return _sha256_url(url) if url else ""

    def model_post_init(self, __context: object) -> None:
        """Synchronise aliases after initialisation."""
        if not self.url_hash and self.url:
            self.url_hash = _sha256_url(self.url)
        # Sync engagement/influence aliases
        if self.score and not self.upvotes:
            self.upvotes = self.score
        if self.upvotes and not self.score:
            self.score = self.upvotes
        if self.comment_count and not self.comments:
            self.comments = self.comment_count
        if self.comments and not self.comment_count:
            self.comment_count = self.comments
        if self.author_karma and not self.followers:
            self.followers = self.author_karma
        if self.followers and not self.author_karma:
            self.author_karma = self.followers
        if self.raw_sentiment and not self.sentiment:
            self.sentiment = self.raw_sentiment
        if self.sentiment and not self.raw_sentiment:
            self.raw_sentiment = self.sentiment
        if self.is_maintainer_context and not self.is_maintainer:
            self.is_maintainer = self.is_maintainer_context
        if self.is_maintainer and not self.is_maintainer_context:
            self.is_maintainer_context = self.is_maintainer

    def effective_followers(self) -> int:
        return self.followers or self.author_karma

    def effective_upvotes(self) -> int:
        return self.upvotes or self.score

    def effective_comments(self) -> int:
        return self.comments or self.comment_count


class ScoredPost(RawPost):
    """A RawPost enriched with normalised scoring signals."""

    influence_norm: float = 0.0
    engagement_norm: float = 0.0
    pain_factor: float = 1.0
    sentiment_factor: float = 1.0
    maintainer_boost: float = 1.0
    final_score: float = 0.0
    signal_score: float = 0.0  # alias for final_score
    provenance: str = "live"
    llm_summary: str = ""

    def model_post_init(self, __context: object) -> None:
        super().model_post_init(__context)
        if self.signal_score and not self.final_score:
            self.final_score = self.signal_score
        if self.final_score and not self.signal_score:
            self.signal_score = self.final_score
        if self.provenance and self.provenance != "live" and self.source_tier == "live":
            self.source_tier = self.provenance
        if self.source_tier and self.source_tier != "live" and self.provenance == "live":
            self.provenance = self.source_tier
        if self.backfill_source != "live" and self.source_tier == "live":
            self.source_tier = self.backfill_source


class DailyReport(BaseModel):
    """Output of a single daily pipeline run."""

    report_date: datetime = Field(default_factory=datetime.utcnow)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    entries: List[ScoredPost] = Field(default_factory=list)
    top_posts: List[ScoredPost] = Field(default_factory=list)  # alias
    entry_count: int = 0
    provenance_breakdown: Dict[str, int] = Field(default_factory=dict)
    scraper_statuses: Dict[str, str] = Field(default_factory=dict)
    total_collected: int = 0
    total_after_filter: int = 0
    is_partial: bool = False
    run_id: int = 0

    def model_post_init(self, __context: object) -> None:
        # Synchronise entry/top_posts lists
        if self.entries and not self.top_posts:
            self.top_posts = self.entries
        if self.top_posts and not self.entries:
            self.entries = self.top_posts
        if not self.entry_count:
            self.entry_count = len(self.entries or self.top_posts)
        if not self.is_partial:
            self.is_partial = self.entry_count < 5


class WeeklyReport(BaseModel):
    """Output of a weekly digest run."""

    week_start: datetime
    week_end: Optional[datetime] = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    entries: List[ScoredPost] = Field(default_factory=list)
    top_posts: List[ScoredPost] = Field(default_factory=list)  # alias
    daily_reports: List[DailyReport] = Field(default_factory=list)
    trend_analysis: Dict[str, object] = Field(default_factory=dict)
    platform_breakdown: Dict[str, int] = Field(default_factory=dict)
    category_breakdown: Dict[str, int] = Field(default_factory=dict)
    run_count: int = 0

    def model_post_init(self, __context: object) -> None:
        if self.entries and not self.top_posts:
            self.top_posts = self.entries
        if self.top_posts and not self.entries:
            self.entries = self.top_posts
