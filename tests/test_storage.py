"""Tests for SQLite database layer."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from radar.models import PainCategory, ScoredPost


def make_scored_post(
    url: str = "https://example.com/post",
    title: str = "Test post about burnout",
    platform: str = "hackernews",
    signal_score: float = 0.75,
    pain_categories: list | None = None,
    is_maintainer: bool = True,
) -> ScoredPost:
    if pain_categories is None:
        pain_categories = [PainCategory.BURNOUT]
    return ScoredPost(
        url=url,
        title=title,
        body="I maintain this project and I'm burned out",
        platform=platform,
        author="testuser",
        followers=500,
        author_karma=500,
        upvotes=100,
        score=100,
        comments=20,
        comment_count=20,
        pain_categories=pain_categories,
        pain_score=2.5,
        sentiment=-0.4,
        raw_sentiment=-0.4,
        is_maintainer=is_maintainer,
        is_maintainer_context=is_maintainer,
        influence_norm=0.6,
        engagement_norm=0.7,
        pain_factor=1.2,
        sentiment_factor=1.4,
        maintainer_boost=1.25,
        final_score=signal_score,
        signal_score=signal_score,
        source_tier="live",
        provenance="live",
    )


class TestDatabaseInit:
    def test_creates_tables(self, tmp_db):
        # Tables should exist
        tables = tmp_db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row[0] for row in tables}
        assert "posts" in table_names
        assert "reports" in table_names
        assert "report_entries" in table_names

    def test_wal_mode_enabled(self, tmp_db):
        mode = tmp_db._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"


class TestPostUpsert:
    def test_insert_new_post(self, tmp_db):
        post = make_scored_post()
        rowid = tmp_db.upsert_post(post)
        assert rowid is not None
        assert rowid > 0

    def test_duplicate_url_hash_skipped(self, tmp_db):
        post = make_scored_post(url="https://example.com/dup")
        id1 = tmp_db.upsert_post(post)
        id2 = tmp_db.upsert_post(post)  # same url_hash
        assert id1 == id2  # returns existing row id

    def test_different_urls_both_inserted(self, tmp_db):
        post1 = make_scored_post(url="https://example.com/a")
        post2 = make_scored_post(url="https://example.com/b")
        id1 = tmp_db.upsert_post(post1)
        id2 = tmp_db.upsert_post(post2)
        assert id1 != id2

    def test_pain_categories_serialised(self, tmp_db):
        post = make_scored_post(
            url="https://example.com/cats",
            pain_categories=[PainCategory.BURNOUT, PainCategory.CI_CD],
        )
        tmp_db.upsert_post(post)
        row = tmp_db._conn.execute(
            "SELECT pain_categories FROM posts WHERE url_hash=?", (post.url_hash,)
        ).fetchone()
        cats = json.loads(row[0])
        assert "burnout" in cats
        assert "ci_cd" in cats


class TestReportCrud:
    def test_create_report(self, tmp_db):
        report_id = tmp_db.create_report("daily", "2024-01-15")
        assert report_id > 0

    def test_duplicate_report_returns_same_id(self, tmp_db):
        id1 = tmp_db.create_report("daily", "2024-01-15")
        id2 = tmp_db.create_report("daily", "2024-01-15")
        assert id1 == id2

    def test_update_report_status(self, tmp_db):
        report_id = tmp_db.create_report("daily", "2024-01-16")
        tmp_db.update_report(report_id=report_id, entry_count=5, status="sent")
        row = tmp_db._conn.execute(
            "SELECT status, entry_count FROM reports WHERE id=?", (report_id,)
        ).fetchone()
        assert row["status"] == "sent"
        assert row["entry_count"] == 5

    def test_add_report_entry(self, tmp_db):
        post = make_scored_post(url="https://example.com/entry")
        post_id = tmp_db.upsert_post(post)
        report_id = tmp_db.create_report("daily", "2024-01-17")
        tmp_db.add_report_entry(report_id=report_id, post_id=post_id, rank=1)
        row = tmp_db._conn.execute(
            "SELECT * FROM report_entries WHERE report_id=? AND post_id=?",
            (report_id, post_id),
        ).fetchone()
        assert row is not None
        assert row["rank"] == 1


class TestDuplicateRunCheck:
    def test_no_recent_report_returns_false(self, tmp_db):
        assert tmp_db.check_duplicate_run(hours=20) is False

    def test_recent_sent_report_returns_true(self, tmp_db):
        report_id = tmp_db.create_report("daily", "2024-01-15")
        tmp_db.update_report(report_id=report_id, entry_count=5, status="sent")
        assert tmp_db.check_duplicate_run(hours=20) is True

    def test_only_sent_reports_trigger_guard(self, tmp_db):
        report_id = tmp_db.create_report("daily", "2024-01-15")
        tmp_db.update_report(report_id=report_id, entry_count=0, status="failed")
        assert tmp_db.check_duplicate_run(hours=20) is False


class TestFetchArchive:
    def test_returns_unreported_posts(self, tmp_db):
        post = make_scored_post(url="https://example.com/archive")
        tmp_db.upsert_post(post)
        results = tmp_db.fetch_archive(days=7, limit=10)
        assert len(results) == 1

    def test_reported_posts_excluded(self, tmp_db):
        post = make_scored_post(url="https://example.com/reported")
        post_id = tmp_db.upsert_post(post)
        tmp_db.mark_reported(post_id)
        results = tmp_db.fetch_archive(days=7, limit=10)
        assert len(results) == 0

    def test_sorted_by_signal_score(self, tmp_db):
        for i, score in enumerate([0.3, 0.9, 0.6], start=1):
            p = make_scored_post(url=f"https://example.com/s{i}", signal_score=score)
            p.final_score = score
            tmp_db.upsert_post(p)

        results = tmp_db.fetch_archive(days=7, limit=10)
        scores = [r.signal_score for r in results]
        assert scores == sorted(scores, reverse=True)


class TestStats:
    def test_initial_stats_zero(self, tmp_db):
        s = tmp_db.get_stats()
        assert s["post_count"] == 0
        assert s["daily_reports_sent"] == 0
        assert s["weekly_reports_sent"] == 0

    def test_post_count_increments(self, tmp_db):
        tmp_db.upsert_post(make_scored_post(url="https://a.com/1"))
        tmp_db.upsert_post(make_scored_post(url="https://a.com/2"))
        s = tmp_db.get_stats()
        assert s["post_count"] == 2
