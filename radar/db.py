"""CatalogDB — sealed-test-compatible facade over the storage.database module."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional


def _now_iso() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()


class CatalogDB:
    """SQLite catalog with WAL mode, URL dedup, and duplicate-run detection.

    Interface expected by sealed acceptance tests.
    """

    def __init__(self, path: str) -> None:
        self.path = str(Path(path).expanduser().resolve())
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create tables and enable WAL mode.  Idempotent."""
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        is_new = not Path(self.path).exists()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        if is_new:
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS posts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                url         TEXT    NOT NULL,
                url_hash    TEXT    UNIQUE NOT NULL,
                title       TEXT    NOT NULL DEFAULT '',
                body        TEXT    DEFAULT '',
                platform    TEXT    NOT NULL DEFAULT '',
                author      TEXT    DEFAULT '',
                score       INTEGER DEFAULT 0,
                num_comments INTEGER DEFAULT 0,
                pain_category TEXT  DEFAULT '',
                source_tier TEXT    DEFAULT 'live',
                sentiment_score REAL DEFAULT 0.0,
                signal_score REAL   DEFAULT 0.0,
                created_at  TEXT    NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS reports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT    NOT NULL DEFAULT '',
                entry_count INTEGER DEFAULT 0,
                source_tier TEXT    DEFAULT 'live',
                status      TEXT    NOT NULL DEFAULT 'created'
            );

            CREATE TABLE IF NOT EXISTS report_entries (
                report_id   INTEGER NOT NULL REFERENCES reports(id),
                post_id     INTEGER NOT NULL,
                rank        INTEGER NOT NULL DEFAULT 0,
                signal_score REAL   DEFAULT 0.0,
                source_tier TEXT    DEFAULT 'live',
                url         TEXT    DEFAULT '',
                title       TEXT    DEFAULT '',
                platform    TEXT    DEFAULT '',
                PRIMARY KEY (report_id, post_id)
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "CatalogDB":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Posts
    # ------------------------------------------------------------------

    def insert_post(self, post: dict) -> Optional[int]:
        """Insert a post dict; silently skip if url_hash already exists."""
        assert self._conn is not None
        url_hash = post.get("url_hash") or ""
        if not url_hash:
            import hashlib
            url_hash = hashlib.sha256(post.get("url", "").encode()).hexdigest()

        existing = self._conn.execute(
            "SELECT id FROM posts WHERE url_hash = ?", (url_hash,)
        ).fetchone()
        if existing:
            return int(existing["id"])

        now = _now_iso()
        cur = self._conn.execute(
            """
            INSERT INTO posts (
                url, url_hash, title, body, platform, author,
                score, num_comments, pain_category, source_tier,
                sentiment_score, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post.get("url", ""),
                url_hash,
                post.get("title", ""),
                post.get("body", ""),
                post.get("platform", ""),
                post.get("author", ""),
                post.get("score", 0),
                post.get("num_comments", 0),
                post.get("pain_category", ""),
                post.get("source_tier", "live"),
                post.get("sentiment_score", 0.0),
                now,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def count_posts(self) -> int:
        assert self._conn is not None
        return self._conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]

    # ------------------------------------------------------------------
    # Reports / duplicate-run guard
    # ------------------------------------------------------------------

    def record_report(
        self,
        created_at: Optional[datetime] = None,
        entry_count: int = 0,
        source_tier: str = "live",
    ) -> int:
        """Record a completed report run."""
        assert self._conn is not None
        ts = created_at.replace(tzinfo=timezone.utc).isoformat() if created_at else _now_iso()
        cur = self._conn.execute(
            "INSERT INTO reports (created_at, entry_count, source_tier, status) VALUES (?, ?, ?, 'sent')",
            (ts, entry_count, source_tier),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def has_recent_report(self, window_hours: int = 20) -> bool:
        """Return True if a report exists within the last *window_hours* hours."""
        assert self._conn is not None
        cutoff = (
            datetime.utcnow() - timedelta(hours=window_hours)
        ).replace(tzinfo=timezone.utc).isoformat()
        row = self._conn.execute(
            "SELECT id FROM reports WHERE created_at > ? AND status = 'sent' LIMIT 1",
            (cutoff,),
        ).fetchone()
        return row is not None

    def create_report(self) -> int:
        """Create a new report row; return its id."""
        assert self._conn is not None
        now = _now_iso()
        cur = self._conn.execute(
            "INSERT INTO reports (created_at, entry_count, source_tier, status) VALUES (?, 0, 'live', 'created')",
            (now,),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Report entries
    # ------------------------------------------------------------------

    def insert_report_entry(
        self,
        report_id: int,
        post: dict,
        rank: int,
        signal_score: float = 0.0,
    ) -> None:
        """Link a post dict to a report."""
        assert self._conn is not None
        url_hash = post.get("url_hash") or ""
        if not url_hash:
            import hashlib
            url_hash = hashlib.sha256(post.get("url", "").encode()).hexdigest()

        # Ensure the post exists
        existing = self._conn.execute(
            "SELECT id FROM posts WHERE url_hash = ?", (url_hash,)
        ).fetchone()
        if existing:
            post_id = int(existing["id"])
        else:
            post_id = self.insert_post(post) or 0

        try:
            self._conn.execute(
                """
                INSERT INTO report_entries
                    (report_id, post_id, rank, signal_score, source_tier, url, title, platform)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    post_id,
                    rank,
                    signal_score,
                    post.get("source_tier", "live"),
                    post.get("url", ""),
                    post.get("title", ""),
                    post.get("platform", ""),
                ),
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            pass

    def get_report_entries(self, report_id: int) -> List[Dict]:
        """Return entries for a report as list of dicts."""
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT * FROM report_entries WHERE report_id = ? ORDER BY rank",
            (report_id,),
        ).fetchall()
        return [dict(row) for row in rows]
