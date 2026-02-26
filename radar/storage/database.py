"""SQLite WAL-mode catalog for OSS Radar with SHA-256 URL deduplication."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from radar.models import PainCategory, ScoredPost


def _now_iso() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()


class Database:
    """Thin SQLite wrapper with WAL mode, parameterised queries, and dedup.

    The DB file is created with permissions 0600 (owner r/w only).
    """

    def __init__(self, path: str = "~/.radar/catalog.db") -> None:
        self.path = str(Path(path).expanduser().resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = self._open()
        self._migrate()

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _open(self) -> sqlite3.Connection:
        """Open connection; create file with 0600 perms if new."""
        is_new = not Path(self.path).exists()
        conn = sqlite3.connect(self.path, check_same_thread=False)
        if is_new:
            os.chmod(self.path, 0o600)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def close(self) -> None:
        """Close the underlying connection."""
        if self._conn:
            self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Schema migration
    # ------------------------------------------------------------------

    def _migrate(self) -> None:
        """Create tables if they do not yet exist."""
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS posts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                url          TEXT    NOT NULL,
                url_hash     TEXT    UNIQUE NOT NULL,
                title        TEXT    NOT NULL DEFAULT '',
                body         TEXT    DEFAULT '',
                platform     TEXT    NOT NULL DEFAULT '',
                author       TEXT    DEFAULT '',
                followers    INTEGER DEFAULT 0,
                upvotes      INTEGER DEFAULT 0,
                comments     INTEGER DEFAULT 0,
                tags         TEXT    DEFAULT '[]',
                pain_categories TEXT DEFAULT '[]',
                pain_score   REAL    DEFAULT 0.0,
                sentiment    REAL    DEFAULT 0.0,
                final_score  REAL    DEFAULT 0.0,
                signal_score REAL    DEFAULT 0.0,
                influence_norm REAL  DEFAULT 0.0,
                engagement_norm REAL DEFAULT 0.0,
                pain_factor  REAL    DEFAULT 1.0,
                sentiment_factor REAL DEFAULT 1.0,
                maintainer_boost REAL DEFAULT 1.0,
                is_maintainer INTEGER DEFAULT 0,
                source_tier  TEXT    DEFAULT 'live',
                backfill_source TEXT DEFAULT 'live',
                scraped_at   TEXT    NOT NULL DEFAULT '',
                created_at   TEXT    NOT NULL DEFAULT '',
                reported_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS reports (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type  TEXT    NOT NULL CHECK (report_type IN ('daily','weekly')),
                report_date  TEXT    NOT NULL,
                entry_count  INTEGER DEFAULT 0,
                sent_at      TEXT,
                status       TEXT    NOT NULL DEFAULT 'created'
                             CHECK (status IN ('created','sent','failed')),
                created_at   TEXT    NOT NULL DEFAULT '',
                UNIQUE (report_type, report_date)
            );

            CREATE TABLE IF NOT EXISTS report_entries (
                report_id    INTEGER NOT NULL REFERENCES reports(id),
                post_id      INTEGER NOT NULL REFERENCES posts(id),
                rank         INTEGER NOT NULL DEFAULT 0,
                provenance   TEXT    DEFAULT 'live',
                PRIMARY KEY (report_id, post_id)
            );

            CREATE INDEX IF NOT EXISTS idx_posts_scraped_at
                ON posts(scraped_at);
            CREATE INDEX IF NOT EXISTS idx_posts_signal_score
                ON posts(signal_score DESC);
            CREATE INDEX IF NOT EXISTS idx_posts_reported_at
                ON posts(reported_at);
            CREATE INDEX IF NOT EXISTS idx_reports_type_date
                ON reports(report_type, report_date);
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Post CRUD
    # ------------------------------------------------------------------

    def upsert_post(self, post: ScoredPost) -> Optional[int]:
        """Insert post; silently skip if url_hash already exists.

        Returns the rowid of the existing or newly-inserted row.
        """
        existing = self._conn.execute(
            "SELECT id FROM posts WHERE url_hash = ?", (post.url_hash,)
        ).fetchone()
        if existing:
            return int(existing["id"])

        now = _now_iso()
        scraped = post.scraped_at.isoformat() if post.scraped_at else now
        cats_json = json.dumps([c.value for c in post.pain_categories])
        tags_json = json.dumps(post.tags)

        cur = self._conn.execute(
            """
            INSERT INTO posts (
                url, url_hash, title, body, platform, author,
                followers, upvotes, comments, tags,
                pain_categories, pain_score, sentiment, final_score, signal_score,
                influence_norm, engagement_norm, pain_factor, sentiment_factor,
                maintainer_boost, is_maintainer, source_tier, backfill_source,
                scraped_at, created_at
            ) VALUES (
                ?,?,?,?,?,?,
                ?,?,?,?,
                ?,?,?,?,?,
                ?,?,?,?,
                ?,?,?,?,
                ?,?
            )
            """,
            (
                post.url, post.url_hash, post.title, post.body,
                post.platform, post.author,
                post.effective_followers(), post.effective_upvotes(),
                post.effective_comments(), tags_json,
                cats_json, post.pain_score, post.sentiment,
                post.final_score, post.signal_score,
                post.influence_norm, post.engagement_norm,
                post.pain_factor, post.sentiment_factor,
                post.maintainer_boost, int(post.is_maintainer),
                post.source_tier, post.backfill_source,
                scraped, now,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def mark_reported(self, post_id: int) -> None:
        """Set reported_at = now for the given post row."""
        self._conn.execute(
            "UPDATE posts SET reported_at = ? WHERE id = ?",
            (_now_iso(), post_id),
        )
        self._conn.commit()

    def fetch_archive(self, days: int, limit: int = 50) -> List[ScoredPost]:
        """Return unreported posts from the last *days* days, ordered by signal_score."""
        cutoff = (
            datetime.utcnow() - timedelta(days=days)
        ).replace(tzinfo=timezone.utc).isoformat()

        rows = self._conn.execute(
            """
            SELECT * FROM posts
            WHERE scraped_at >= ?
              AND reported_at IS NULL
            ORDER BY signal_score DESC
            LIMIT ?
            """,
            (cutoff, limit),
        ).fetchall()

        return [self._row_to_scored(row) for row in rows]

    def fetch_all_unreported(self, limit: int = 50) -> List[ScoredPost]:
        """Return all unreported posts ordered by signal_score."""
        rows = self._conn.execute(
            """
            SELECT * FROM posts
            WHERE reported_at IS NULL
            ORDER BY signal_score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_scored(row) for row in rows]

    # ------------------------------------------------------------------
    # Report CRUD
    # ------------------------------------------------------------------

    def create_report(self, report_type: str, report_date: str) -> int:
        """Insert a new report row; return its id."""
        now = _now_iso()
        try:
            cur = self._conn.execute(
                """
                INSERT INTO reports (report_type, report_date, created_at)
                VALUES (?, ?, ?)
                """,
                (report_type, report_date, now),
            )
            self._conn.commit()
            return cur.lastrowid  # type: ignore[return-value]
        except sqlite3.IntegrityError:
            # Already exists
            row = self._conn.execute(
                "SELECT id FROM reports WHERE report_type=? AND report_date=?",
                (report_type, report_date),
            ).fetchone()
            return int(row["id"])

    def update_report(
        self,
        report_id: int,
        entry_count: int,
        status: str = "sent",
        sent_at: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE reports
               SET entry_count = ?, status = ?, sent_at = ?
             WHERE id = ?
            """,
            (entry_count, status, sent_at or _now_iso(), report_id),
        )
        self._conn.commit()

    def add_report_entry(
        self, report_id: int, post_id: int, rank: int, provenance: str = "live"
    ) -> None:
        """Link a post to a report."""
        try:
            self._conn.execute(
                """
                INSERT INTO report_entries (report_id, post_id, rank, provenance)
                VALUES (?, ?, ?, ?)
                """,
                (report_id, post_id, rank, provenance),
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            pass  # already linked

    def check_duplicate_run(self, hours: int = 20) -> bool:
        """Return True if a successful daily report exists within the last *hours*."""
        cutoff = (
            datetime.utcnow() - timedelta(hours=hours)
        ).replace(tzinfo=timezone.utc).isoformat()

        row = self._conn.execute(
            """
            SELECT id FROM reports
             WHERE report_type = 'daily'
               AND status = 'sent'
               AND created_at >= ?
             LIMIT 1
            """,
            (cutoff,),
        ).fetchone()
        return row is not None

    def get_weekly_posts(
        self, week_start: datetime, week_end: datetime
    ) -> List[ScoredPost]:
        """Return posts reported within [week_start, week_end], ordered by signal_score."""
        start_iso = week_start.isoformat()
        end_iso = week_end.isoformat()

        rows = self._conn.execute(
            """
            SELECT DISTINCT p.*
              FROM posts p
              JOIN report_entries re ON re.post_id = p.id
              JOIN reports r ON r.id = re.report_id
             WHERE p.reported_at >= ?
               AND p.reported_at <= ?
             ORDER BY p.signal_score DESC
             LIMIT 10
            """,
            (start_iso, end_iso),
        ).fetchall()
        return [self._row_to_scored(row) for row in rows]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return a dict with catalog statistics."""
        post_count = self._conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        daily_count = self._conn.execute(
            "SELECT COUNT(*) FROM reports WHERE report_type='daily' AND status='sent'"
        ).fetchone()[0]
        weekly_count = self._conn.execute(
            "SELECT COUNT(*) FROM reports WHERE report_type='weekly' AND status='sent'"
        ).fetchone()[0]
        last_run_row = self._conn.execute(
            "SELECT MAX(created_at) FROM reports"
        ).fetchone()
        last_run = last_run_row[0] if last_run_row else None

        return {
            "post_count": post_count,
            "daily_reports_sent": daily_count,
            "weekly_reports_sent": weekly_count,
            "last_run": last_run,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_scored(row: sqlite3.Row) -> ScoredPost:
        """Convert a DB row to a ScoredPost."""
        d = dict(row)

        # Deserialise JSON fields
        try:
            cats_raw = json.loads(d.get("pain_categories") or "[]")
            cats = [PainCategory(c) for c in cats_raw if c]
        except (json.JSONDecodeError, ValueError):
            cats = []

        try:
            tags = json.loads(d.get("tags") or "[]")
        except json.JSONDecodeError:
            tags = []

        scraped_str = d.get("scraped_at", "")
        try:
            scraped_at = datetime.fromisoformat(scraped_str)
        except (ValueError, TypeError):
            scraped_at = datetime.utcnow()

        final = float(d.get("final_score") or d.get("signal_score") or 0.0)

        return ScoredPost(
            url=d.get("url", ""),
            url_hash=d.get("url_hash", ""),
            title=d.get("title", ""),
            body=d.get("body", "") or "",
            platform=d.get("platform", ""),
            author=d.get("author", "") or "",
            followers=int(d.get("followers") or 0),
            author_karma=int(d.get("followers") or 0),
            upvotes=int(d.get("upvotes") or 0),
            score=int(d.get("upvotes") or 0),
            comments=int(d.get("comments") or 0),
            comment_count=int(d.get("comments") or 0),
            tags=tags,
            pain_categories=cats,
            pain_score=float(d.get("pain_score") or 0.0),
            sentiment=float(d.get("sentiment") or 0.0),
            raw_sentiment=float(d.get("sentiment") or 0.0),
            is_maintainer=bool(d.get("is_maintainer")),
            is_maintainer_context=bool(d.get("is_maintainer")),
            source_tier=d.get("source_tier") or "live",
            backfill_source=d.get("backfill_source") or "live",
            scraped_at=scraped_at,
            influence_norm=float(d.get("influence_norm") or 0.0),
            engagement_norm=float(d.get("engagement_norm") or 0.0),
            pain_factor=float(d.get("pain_factor") or 1.0),
            sentiment_factor=float(d.get("sentiment_factor") or 1.0),
            maintainer_boost=float(d.get("maintainer_boost") or 1.0),
            final_score=final,
            signal_score=final,
            provenance=d.get("source_tier") or "live",
        )
