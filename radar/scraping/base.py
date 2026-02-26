"""Abstract base class for all OSS Radar scrapers."""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import List

from radar.config import Settings
from radar.models import RawPost
from radar.scraping.http import SafeHTTPClient

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Contract that every platform scraper must implement.

    Each subclass sets ``platform`` as a class-level string constant.
    ``scrape()`` wraps ``fetch_raw()`` with logging and error isolation.
    """

    platform: str = "unknown"

    def __init__(self, config: Settings, client: SafeHTTPClient | None = None) -> None:
        self.config = config
        self.client = client or SafeHTTPClient(
            timeout=config.request_timeout,
            max_retries=config.max_retries,
            min_wait=config.retry_min_wait,
            max_wait=config.retry_max_wait,
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def scrape(self) -> List[RawPost]:
        """Fetch posts, log counts, and isolate errors.

        Returns an empty list on any exception so the pipeline continues.
        """
        try:
            posts = self.fetch_raw()
            logger.info(
                "scraper_fetched",
                extra={"platform": self.platform, "count": len(posts)},
            )
            return posts
        except Exception as exc:
            logger.error(
                "scraper_failed",
                extra={"platform": self.platform, "error": str(exc)},
                exc_info=True,
            )
            return []

    # ------------------------------------------------------------------
    # Abstract method
    # ------------------------------------------------------------------

    @abstractmethod
    def fetch_raw(self) -> List[RawPost]:
        """Fetch posts from the platform and return as RawPost objects."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _dedup_key(self, url: str) -> str:
        """Return SHA-256 hex digest of a normalised URL (dedup key)."""
        normalised = url.strip().lower().rstrip("/")
        return hashlib.sha256(normalised.encode()).hexdigest()

    def _build_post(self, raw: dict) -> RawPost:
        """Build a RawPost from a raw dict with sensible defaults."""
        url = str(raw.get("url", ""))
        return RawPost(
            url=url,
            url_hash=self._dedup_key(url),
            title=str(raw.get("title", "")),
            body=str(raw.get("body", "")),
            platform=self.platform,
            author=str(raw.get("author", "")),
            followers=int(raw.get("followers", 0)),
            author_karma=int(raw.get("author_karma", 0)),
            upvotes=int(raw.get("upvotes", 0)),
            score=int(raw.get("score", 0)),
            comments=int(raw.get("comments", 0)),
            comment_count=int(raw.get("comment_count", 0)),
            tags=list(raw.get("tags", [])),
        )
