"""Shared pytest fixtures for OSS Radar test suite."""

from __future__ import annotations

import os
import random
import tempfile
from datetime import datetime, timezone
from typing import List

import pytest

# Ensure no real env vars bleed in during tests
os.environ.setdefault("RADAR_EMAIL_ENABLED", "false")
os.environ.setdefault("RADAR_REDDIT_ENABLED", "false")

# ─── Anti-Flake Guardrails ───

FROZEN_TIME = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _deterministic_seed():
    """Reset random seed before every test to prevent ordering-dependent flakes."""
    random.seed(42)
    yield


@pytest.fixture(autouse=True)
def _freeze_time(monkeypatch):
    """Freeze datetime.now()/utcnow() to a deterministic value."""
    import datetime as dt_module

    _real_datetime = datetime

    class FrozenDatetime(_real_datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_TIME

        @classmethod
        def utcnow(cls):
            return FROZEN_TIME.replace(tzinfo=None)

    monkeypatch.setattr(dt_module, "datetime", FrozenDatetime)


@pytest.fixture()
def tmp_db(tmp_path):
    """Return a Database instance backed by a temporary file."""
    from radar.storage.database import Database

    db_path = str(tmp_path / "test_catalog.db")
    db = Database(db_path)
    yield db
    db.close()


@pytest.fixture()
def mock_settings(tmp_path):
    """Return a Settings instance with safe test defaults."""
    from radar.config import Settings

    return Settings(
        db_path=str(tmp_path / "test.db"),
        email_enabled=False,
        reddit_enabled=False,
        influence_weight=0.4,
        engagement_weight=0.6,
        log_level="DEBUG",
    )


@pytest.fixture()
def sample_raw_posts() -> List:
    """Return a list of RawPosts that pass all filters."""
    from radar.models import PainCategory, RawPost

    base_text = (
        "I maintain this open source project and we are dealing with severe dependency hell. "
        "We merged a pull request last week but the CI/CD pipeline keeps failing. "
        "This is really frustrating and I'm completely burned out from trying to fix it. "
        "The breaking changes in v3.0 have caused nothing but problems for our library."
    )
    posts = []
    for i in range(6):
        p = RawPost(
            url=f"https://news.ycombinator.com/item?id={10000 + i}",
            title=f"I maintain an OSS project and CI keeps failing — help",
            body=base_text,
            platform="hackernews",
            author=f"user{i}",
            followers=100 * (i + 1),
            author_karma=100 * (i + 1),
            upvotes=50 * (i + 1),
            score=50 * (i + 1),
            comments=10 * (i + 1),
            comment_count=10 * (i + 1),
            tags=["ask_hn"],
            pain_categories=[PainCategory.CI_CD, PainCategory.BURNOUT],
            pain_score=3.5,
            sentiment=-0.4,
            raw_sentiment=-0.4,
            is_maintainer=True,
            is_maintainer_context=True,
        )
        posts.append(p)
    return posts


@pytest.fixture()
def sample_scored_posts(sample_raw_posts):
    """Return scored versions of sample_raw_posts."""
    from radar.ranking.scorer import SignalScorer

    scorer = SignalScorer()
    return scorer.score_batch(sample_raw_posts)
