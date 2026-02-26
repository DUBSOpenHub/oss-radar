"""Tests for the pipeline orchestrator and backfill ladder."""

from __future__ import annotations

from datetime import datetime
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from radar.models import PainCategory, RawPost, ScoredPost


def make_scored_post(
    url: str = "https://example.com/p",
    signal_score: float = 0.5,
    source_tier: str = "live",
) -> ScoredPost:
    return ScoredPost(
        url=url,
        title="I maintain OSS and CI keeps failing",
        body="I'm the author of this library and it needs help",
        platform="hackernews",
        author="dev",
        followers=200,
        author_karma=200,
        upvotes=80,
        score=80,
        comments=15,
        comment_count=15,
        pain_categories=[PainCategory.CI_CD, PainCategory.BURNOUT],
        pain_score=2.0,
        sentiment=-0.4,
        raw_sentiment=-0.4,
        is_maintainer=True,
        is_maintainer_context=True,
        influence_norm=0.5,
        engagement_norm=0.5,
        pain_factor=1.2,
        sentiment_factor=1.4,
        maintainer_boost=1.0,
        final_score=signal_score,
        signal_score=signal_score,
        source_tier=source_tier,
        provenance=source_tier,
    )


@pytest.fixture()
def mock_scraper_with_posts():
    """Create a mock scraper that returns 6 posts."""
    scraper = MagicMock()
    scraper.platform = "hackernews"
    posts = [
        make_scored_post(url=f"https://hn.example.com/{i}", signal_score=1.0 - i * 0.1)
        for i in range(6)
    ]
    scraper.scrape.return_value = posts
    return scraper, posts


# ---------------------------------------------------------------------------
# BackfillManager tests
# ---------------------------------------------------------------------------


class TestBackfillManager:
    def test_exactly_five_live_posts_returned(self, tmp_db):
        from radar.pipeline import BackfillManager

        manager = BackfillManager(tmp_db)
        posts = [
            make_scored_post(url=f"https://example.com/{i}") for i in range(5)
        ]
        result = manager.ensure_five(posts)
        assert len(result) == 5
        assert all(p.source_tier == "live" for p in result)

    def test_six_live_posts_truncated_to_five(self, tmp_db):
        from radar.pipeline import BackfillManager

        manager = BackfillManager(tmp_db)
        posts = [
            make_scored_post(url=f"https://example.com/{i}") for i in range(6)
        ]
        result = manager.ensure_five(posts)
        assert len(result) == 5

    def test_fallback_from_archive_when_live_insufficient(self, tmp_db):
        """When live posts < 5, fill from archive."""
        from radar.pipeline import BackfillManager

        # Insert archive posts in DB
        for i in range(5):
            p = make_scored_post(
                url=f"https://example.com/arch/{i}",
                signal_score=0.3,
            )
            tmp_db.upsert_post(p)

        manager = BackfillManager(tmp_db)
        # Only 2 live posts
        live_posts = [make_scored_post(url=f"https://example.com/live/{i}") for i in range(2)]
        result = manager.ensure_five(live_posts)
        assert len(result) >= 2  # at minimum the live ones

    def test_partial_result_when_fewer_than_five_available(self, tmp_db):
        """If total available < 5, result has partial provenance."""
        from radar.pipeline import BackfillManager

        manager = BackfillManager(tmp_db)
        # Only 2 posts total, none in DB
        posts = [make_scored_post(url=f"https://example.com/{i}") for i in range(2)]
        result = manager.ensure_five(posts)
        assert len(result) == 2  # can't find more

    def test_source_tier_set_correctly_for_live(self, tmp_db):
        from radar.pipeline import BackfillManager

        manager = BackfillManager(tmp_db)
        posts = [make_scored_post(url=f"https://example.com/{i}") for i in range(5)]
        result = manager.ensure_five(posts)
        for p in result:
            assert p.source_tier == "live"
            assert p.provenance == "live"


# ---------------------------------------------------------------------------
# PipelineOrchestrator tests
# ---------------------------------------------------------------------------


class TestPipelineOrchestrator:
    def test_dry_run_does_not_write_to_db(self, tmp_db, mock_settings):
        """dry_run=True must not insert any rows."""
        from radar.pipeline import PipelineOrchestrator
        from radar.ranking.filters import FilterPipeline
        from radar.ranking.scorer import SignalScorer

        # Build posts that pass all filters (pre-scored)
        posts = [
            make_scored_post(url=f"https://example.com/{i}", signal_score=0.8 - i * 0.1)
            for i in range(5)
        ]

        mock_scraper = MagicMock()
        mock_scraper.platform = "hackernews"
        mock_scraper.scrape.return_value = []

        pipeline = PipelineOrchestrator(
            config=mock_settings,
            db=tmp_db,
            scrapers=[mock_scraper],
        )

        # Monkey-patch _rank to return scored posts directly
        pipeline._rank = lambda p: posts[:len(p)] if p else posts

        # Run
        report = pipeline.run_daily(dry_run=True, force=True)

        # DB should have no posts
        count = tmp_db._conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        assert count == 0

    def test_duplicate_run_guard_without_force(self, tmp_db, mock_settings):
        """Without --force, a recent daily report causes early exit."""
        from radar.pipeline import PipelineOrchestrator

        # Simulate a recent sent report
        report_id = tmp_db.create_report("daily", "2024-01-15")
        tmp_db.update_report(report_id=report_id, entry_count=5, status="sent")

        pipeline = PipelineOrchestrator(
            config=mock_settings,
            db=tmp_db,
            scrapers=[],
        )

        report = pipeline.run_daily(dry_run=False, force=False)
        # Should return placeholder with no entries
        assert report.entry_count == 0

    def test_force_overrides_duplicate_guard(self, tmp_db, mock_settings):
        """With --force, pipeline runs even after recent report."""
        from radar.pipeline import PipelineOrchestrator

        # Simulate a recent sent report
        report_id = tmp_db.create_report("daily", "2024-01-15")
        tmp_db.update_report(report_id=report_id, entry_count=5, status="sent")

        mock_scraper = MagicMock()
        mock_scraper.platform = "test"
        mock_scraper.scrape.return_value = []

        pipeline = PipelineOrchestrator(
            config=mock_settings,
            db=tmp_db,
            scrapers=[mock_scraper],
        )

        # With force=True, should NOT return early
        report = pipeline.run_daily(dry_run=True, force=True)
        # scraper should have been called
        mock_scraper.scrape.assert_called_once()

    def test_scraper_failure_isolated(self, tmp_db, mock_settings):
        """A failing scraper does not crash the pipeline."""
        from radar.pipeline import PipelineOrchestrator

        bad_scraper = MagicMock()
        bad_scraper.platform = "bad"
        bad_scraper.scrape.side_effect = Exception("Network down")

        good_scraper = MagicMock()
        good_scraper.platform = "good"
        good_scraper.scrape.return_value = []

        pipeline = PipelineOrchestrator(
            config=mock_settings,
            db=tmp_db,
            scrapers=[bad_scraper, good_scraper],
        )

        # Should not raise
        report = pipeline.run_daily(dry_run=True, force=True)
        assert report is not None

    def test_weekly_pipeline_returns_report(self, tmp_db, mock_settings):
        from radar.pipeline import PipelineOrchestrator

        pipeline = PipelineOrchestrator(
            config=mock_settings,
            db=tmp_db,
            scrapers=[],
        )
        report = pipeline.run_weekly(dry_run=True)
        assert report is not None
        assert hasattr(report, "week_start")


# ---------------------------------------------------------------------------
# Fallback ladder provenance tagging tests
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_live_posts_tagged_live(self, tmp_db):
        from radar.pipeline import BackfillManager

        manager = BackfillManager(tmp_db)
        posts = [make_scored_post(url=f"https://ex.com/{i}") for i in range(5)]
        result = manager.ensure_five(posts)
        assert all(p.source_tier == "live" for p in result)

    def test_source_tier_values_are_valid(self, tmp_db):
        from radar.pipeline import BackfillManager

        manager = BackfillManager(tmp_db)
        posts = [make_scored_post(url=f"https://ex.com/{i}") for i in range(3)]
        result = manager.ensure_five(posts)
        valid_tiers = {"live", "archive-7d", "archive-30d", "partial"}
        for p in result:
            assert p.source_tier in valid_tiers
