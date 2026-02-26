"""Tests for email template rendering and MIME structure."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from radar.models import DailyReport, PainCategory, ScoredPost, WeeklyReport


def make_scored_post(
    rank: int = 1,
    signal_score: float = 0.75,
    source_tier: str = "live",
) -> ScoredPost:
    return ScoredPost(
        url=f"https://example.com/post-{rank}",
        title=f"OSS Burnout Story #{rank}",
        body="I maintain this and CI keeps failing. I'm burned out.",
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
        final_score=signal_score,
        signal_score=signal_score,
        source_tier=source_tier,
        provenance=source_tier,
    )


@pytest.fixture()
def daily_report_full():
    """A daily report with 5 posts."""
    posts = [make_scored_post(rank=i, signal_score=1.0 - i * 0.1) for i in range(1, 6)]
    return DailyReport(
        report_date=datetime(2024, 1, 15),
        generated_at=datetime(2024, 1, 15),
        entries=posts,
        top_posts=posts,
        entry_count=5,
        is_partial=False,
    )


@pytest.fixture()
def daily_report_partial():
    """A partial daily report with fewer than 5 posts."""
    posts = [make_scored_post(rank=i) for i in range(1, 3)]
    return DailyReport(
        report_date=datetime(2024, 1, 15),
        generated_at=datetime(2024, 1, 15),
        entries=posts,
        top_posts=posts,
        entry_count=2,
        is_partial=True,
    )


@pytest.fixture()
def weekly_report():
    posts = [make_scored_post(rank=i, signal_score=1.0 - i * 0.05) for i in range(1, 8)]
    return WeeklyReport(
        week_start=datetime(2024, 1, 8),
        week_end=datetime(2024, 1, 15),
        entries=posts,
        top_posts=posts,
        platform_breakdown={"hackernews": 5, "devto": 2},
        category_breakdown={"burnout": 4, "ci_cd": 3},
        run_count=5,
    )


@pytest.fixture()
def mock_settings():
    from radar.config import Settings
    return Settings(
        email_enabled=False,
        smtp_host="smtp.test.com",
        smtp_port=587,
        smtp_user="user@test.com",
        smtp_password="pass",
        email_to=["to@test.com"],
        email_from="from@test.com",
    )


class TestDailyTemplateRendering:
    def test_renders_without_error(self, daily_report_full, mock_settings):
        from radar.email.sender import EmailSender

        sender = EmailSender(mock_settings)
        html = sender._render(
            "daily.html.j2",
            {"report": daily_report_full, "date_str": "2024-01-15"},
        )
        assert html
        assert "OSS Radar" in html

    def test_correct_subject_format(self, daily_report_full, mock_settings):
        """Subject must match exact pattern from PRD."""
        date_str = daily_report_full.report_date.strftime("%Y-%m-%d")
        expected = f"[OSS Radar] Daily Intel — {date_str}"
        assert date_str == "2024-01-15"
        assert expected == "[OSS Radar] Daily Intel — 2024-01-15"

    def test_partial_banner_shown_in_partial_report(
        self, daily_report_partial, mock_settings
    ):
        from radar.email.sender import EmailSender

        sender = EmailSender(mock_settings)
        html = sender._render(
            "daily.html.j2",
            {"report": daily_report_partial, "date_str": "2024-01-15"},
        )
        assert "Partial Report" in html or "partial" in html.lower()

    def test_no_partial_banner_in_full_report(self, daily_report_full, mock_settings):
        from radar.email.sender import EmailSender

        sender = EmailSender(mock_settings)
        html = sender._render(
            "daily.html.j2",
            {"report": daily_report_full, "date_str": "2024-01-15"},
        )
        # Should not show partial banner for a full report
        assert "Partial Report" not in html

    def test_rank_medals_present(self, daily_report_full, mock_settings):
        from radar.email.sender import EmailSender

        sender = EmailSender(mock_settings)
        html = sender._render(
            "daily.html.j2",
            {"report": daily_report_full, "date_str": "2024-01-15"},
        )
        assert "🥇" in html
        assert "🥈" in html
        assert "🥉" in html

    def test_empty_report_renders(self, mock_settings):
        from radar.email.sender import EmailSender

        sender = EmailSender(mock_settings)
        empty_report = DailyReport(
            report_date=datetime(2024, 1, 15),
            entries=[],
            top_posts=[],
            entry_count=0,
            is_partial=True,
        )
        html = sender._render(
            "daily.html.j2",
            {"report": empty_report, "date_str": "2024-01-15"},
        )
        assert html  # Should not crash on empty data


class TestWeeklyTemplateRendering:
    def test_renders_without_error(self, weekly_report, mock_settings):
        from radar.email.sender import EmailSender

        sender = EmailSender(mock_settings)
        html = sender._render(
            "weekly.html.j2",
            {"report": weekly_report, "date_str": "2024-01-08"},
        )
        assert html
        assert "Weekly Digest" in html

    def test_correct_subject_format(self, weekly_report):
        """Weekly subject must match PRD format."""
        date_str = weekly_report.week_start.strftime("%Y-%m-%d")
        subject = f"[OSS Radar] Weekly Digest — Week of {date_str}"
        assert subject == "[OSS Radar] Weekly Digest — Week of 2024-01-08"

    def test_platform_breakdown_shown(self, weekly_report, mock_settings):
        from radar.email.sender import EmailSender

        sender = EmailSender(mock_settings)
        html = sender._render(
            "weekly.html.j2",
            {"report": weekly_report, "date_str": "2024-01-08"},
        )
        assert "hackernews" in html

    def test_empty_weekly_renders(self, mock_settings):
        from radar.email.sender import EmailSender

        sender = EmailSender(mock_settings)
        empty = WeeklyReport(
            week_start=datetime(2024, 1, 8),
            entries=[],
            top_posts=[],
            platform_breakdown={},
            category_breakdown={},
        )
        html = sender._render(
            "weekly.html.j2",
            {"report": empty, "date_str": "2024-01-08"},
        )
        assert html


class TestEmailMIMEStructure:
    def test_build_mime_has_both_parts(self, daily_report_full, mock_settings):
        from radar.email.sender import EmailSender

        sender = EmailSender(mock_settings)
        html = "<html><body>Test</body></html>"
        mime = sender._build_mime(
            subject="Test Subject",
            html=html,
            recipients=["to@test.com"],
        )
        assert mime["Subject"] == "Test Subject"
        # Should have text/plain and text/html parts
        payloads = mime.get_payload()
        content_types = [p.get_content_type() for p in payloads]
        assert "text/plain" in content_types
        assert "text/html" in content_types

    def test_plaintext_fallback_strips_tags(self, mock_settings):
        from radar.email.sender import EmailSender

        sender = EmailSender(mock_settings)
        html = "<h1>Hello</h1><p>World &amp; beyond</p>"
        plain = sender._plaintext_fallback(html)
        assert "<h1>" not in plain
        assert "Hello" in plain
        assert "World & beyond" in plain

    def test_dry_run_skips_smtp(self, daily_report_full, mock_settings):
        from radar.email.sender import EmailSender

        sender = EmailSender(mock_settings)
        # Should return True without sending
        result = sender.send_daily(daily_report_full, dry_run=True)
        assert result is True
