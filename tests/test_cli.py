"""Tests for the Typer CLI commands using CliRunner."""

from __future__ import annotations

from datetime import datetime
from typing import List
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from radar.cli import app
from radar.models import DailyReport, PainCategory, ScoredPost, WeeklyReport


runner = CliRunner()


def make_scored_post(i: int = 1) -> ScoredPost:
    return ScoredPost(
        url=f"https://example.com/post-{i}",
        title=f"I maintain OSS and it is broken #{i}",
        body="Burnout and CI/CD failures everywhere",
        platform="hackernews",
        author="dev",
        followers=500,
        author_karma=500,
        upvotes=100,
        score=100,
        comments=20,
        comment_count=20,
        pain_categories=[PainCategory.BURNOUT, PainCategory.CI_CD],
        pain_score=3.0,
        sentiment=-0.5,
        raw_sentiment=-0.5,
        is_maintainer=True,
        is_maintainer_context=True,
        influence_norm=0.6,
        engagement_norm=0.7,
        pain_factor=1.2,
        sentiment_factor=1.5,
        maintainer_boost=1.25,
        final_score=0.9 - i * 0.05,
        signal_score=0.9 - i * 0.05,
        source_tier="live",
        provenance="live",
    )


def full_daily_report() -> DailyReport:
    posts = [make_scored_post(i) for i in range(1, 6)]
    return DailyReport(
        report_date=datetime(2024, 1, 15),
        generated_at=datetime(2024, 1, 15),
        entries=posts,
        top_posts=posts,
        entry_count=5,
        is_partial=False,
        run_id=1,
    )


def partial_daily_report() -> DailyReport:
    posts = [make_scored_post(i) for i in range(1, 3)]
    return DailyReport(
        report_date=datetime(2024, 1, 15),
        generated_at=datetime(2024, 1, 15),
        entries=posts,
        top_posts=posts,
        entry_count=2,
        is_partial=True,
        run_id=2,
    )


# ---------------------------------------------------------------------------
# stats command
# ---------------------------------------------------------------------------


class TestStatsCommand:
    def test_stats_exits_zero(self, tmp_path):
        result = runner.invoke(
            app,
            ["stats", "--db-path", str(tmp_path / "test.db")],
        )
        assert result.exit_code == 0

    def test_stats_output_contains_metrics(self, tmp_path):
        result = runner.invoke(
            app,
            ["stats", "--db-path", str(tmp_path / "test.db")],
        )
        assert "post_count" in result.output or "Metric" in result.output


# ---------------------------------------------------------------------------
# scrape command
# ---------------------------------------------------------------------------


class TestScrapeCommand:
    def test_scrape_exits_zero_with_mocked_scrapers(self, tmp_path):
        with patch("radar.pipeline.PipelineOrchestrator._collect") as mock_collect:
            mock_collect.return_value = ([], {"hackernews": "ok"})
            result = runner.invoke(
                app,
                ["scrape", "--db-path", str(tmp_path / "test.db")],
            )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# daily command
# ---------------------------------------------------------------------------


class TestDailyCommand:
    def test_daily_exits_zero_on_full_report(self, tmp_path):
        with patch("radar.pipeline.PipelineOrchestrator.run_daily") as mock_run:
            mock_run.return_value = full_daily_report()
            result = runner.invoke(
                app,
                ["daily", "--db-path", str(tmp_path / "test.db"), "--no-email"],
            )
        # Full report (5 posts, is_partial=False) → exit 0
        assert result.exit_code == 0

    def test_daily_exits_one_on_partial_report(self, tmp_path):
        with patch("radar.pipeline.PipelineOrchestrator.run_daily") as mock_run:
            mock_run.return_value = partial_daily_report()
            result = runner.invoke(
                app,
                ["daily", "--db-path", str(tmp_path / "test.db"), "--no-email"],
            )
        # Partial report → exit 1
        assert result.exit_code == 1

    def test_daily_exits_two_on_exception(self, tmp_path):
        with patch("radar.pipeline.PipelineOrchestrator.run_daily") as mock_run:
            mock_run.side_effect = RuntimeError("Fatal error")
            result = runner.invoke(
                app,
                ["daily", "--db-path", str(tmp_path / "test.db"), "--no-email"],
            )
        assert result.exit_code == 2

    def test_dry_run_flag_passed(self, tmp_path):
        with patch("radar.pipeline.PipelineOrchestrator.run_daily") as mock_run:
            mock_run.return_value = full_daily_report()
            result = runner.invoke(
                app,
                [
                    "daily",
                    "--db-path", str(tmp_path / "test.db"),
                    "--dry-run",
                    "--no-email",
                ],
            )
            _, kwargs = mock_run.call_args
            assert kwargs.get("dry_run") is True

    def test_force_flag_passed(self, tmp_path):
        with patch("radar.pipeline.PipelineOrchestrator.run_daily") as mock_run:
            mock_run.return_value = full_daily_report()
            result = runner.invoke(
                app,
                [
                    "daily",
                    "--db-path", str(tmp_path / "test.db"),
                    "--force",
                    "--no-email",
                ],
            )
            _, kwargs = mock_run.call_args
            assert kwargs.get("force") is True


# ---------------------------------------------------------------------------
# weekly command
# ---------------------------------------------------------------------------


class TestWeeklyCommand:
    def test_weekly_exits_zero(self, tmp_path):
        with patch("radar.pipeline.PipelineOrchestrator.run_weekly") as mock_run:
            mock_run.return_value = WeeklyReport(
                week_start=datetime(2024, 1, 8),
                entries=[make_scored_post(i) for i in range(5)],
                top_posts=[make_scored_post(i) for i in range(5)],
                platform_breakdown={"hackernews": 5},
                category_breakdown={"burnout": 3},
            )
            result = runner.invoke(
                app,
                ["weekly", "--db-path", str(tmp_path / "test.db"), "--no-email"],
            )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# validate command
# ---------------------------------------------------------------------------


class TestValidateCommand:
    def test_validate_fails_gracefully_no_internet(self, tmp_path):
        """validate command should exit 0 or 1 without crashing."""
        # DB check will pass; network checks will likely fail in test env
        result = runner.invoke(
            app,
            ["validate", "--db-path", str(tmp_path / "test.db")],
        )
        # Either 0 (all pass) or 1 (some fail) — not 2 (crash)
        assert result.exit_code in (0, 1)
        # Output should contain a table
        assert "Database" in result.output or "Validation" in result.output


# ---------------------------------------------------------------------------
# Exit code tests
# ---------------------------------------------------------------------------


class TestExitCodes:
    def test_exit_0_full_success(self, tmp_path):
        with patch("radar.pipeline.PipelineOrchestrator.run_daily") as mock:
            mock.return_value = full_daily_report()
            result = runner.invoke(
                app, ["daily", "--db-path", str(tmp_path / "test.db"), "--no-email"]
            )
        assert result.exit_code == 0

    def test_exit_1_partial(self, tmp_path):
        with patch("radar.pipeline.PipelineOrchestrator.run_daily") as mock:
            mock.return_value = partial_daily_report()
            result = runner.invoke(
                app, ["daily", "--db-path", str(tmp_path / "test.db"), "--no-email"]
            )
        assert result.exit_code == 1

    def test_exit_2_total_failure(self, tmp_path):
        with patch("radar.pipeline.PipelineOrchestrator.run_daily") as mock:
            mock.side_effect = Exception("boom")
            result = runner.invoke(
                app, ["daily", "--db-path", str(tmp_path / "test.db"), "--no-email"]
            )
        assert result.exit_code == 2
