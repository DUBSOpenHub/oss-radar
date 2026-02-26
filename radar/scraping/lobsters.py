"""Lobsters JSON feed scraper."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

from radar.config import Settings
from radar.models import RawPost
from radar.scraping.base import BaseScraper
from radar.scraping.http import SafeHTTPClient

logger = logging.getLogger(__name__)

_LOBSTERS_ENDPOINTS = [
    "https://lobste.rs/t/programming.json",
    "https://lobste.rs/t/security.json",
    "https://lobste.rs/newest.json",
    "https://lobste.rs/hottest.json",
]


class LobstersScraper(BaseScraper):
    """Fetches stories from Lobsters JSON feeds."""

    platform = "lobsters"

    def __init__(self, config: Settings, client: SafeHTTPClient | None = None) -> None:
        super().__init__(config, client)

    def fetch_raw(self) -> List[RawPost]:
        """Fetch stories from all configured Lobsters feeds."""
        posts: List[RawPost] = []
        seen_ids: set[str] = set()

        for endpoint in _LOBSTERS_ENDPOINTS:
            try:
                batch = self._fetch_feed(endpoint)
                for post in batch:
                    if post.url_hash not in seen_ids:
                        seen_ids.add(post.url_hash)
                        posts.append(post)
            except Exception as exc:
                logger.warning(
                    "lobsters_feed_failed",
                    extra={"url": endpoint, "error": str(exc)},
                )

        return posts

    def _fetch_feed(self, url: str) -> List[RawPost]:
        """Fetch and parse a single Lobsters JSON feed."""
        response = self.client.get(url)
        stories: List[Dict[str, Any]] = response.json()
        return [self._story_to_post(s) for s in stories]

    def _story_to_post(self, story: Dict[str, Any]) -> RawPost:
        """Convert a Lobsters story dict to a RawPost."""
        story_url = story.get("url", "") or story.get("short_id_url", "")
        # For text posts, use the comments URL
        if not story_url:
            story_url = story.get("comments_url", "")

        title = story.get("title", "")
        body = story.get("description", "") or ""

        author = story.get("submitter_user", {})
        if isinstance(author, dict):
            author_name = author.get("username", "")
        else:
            author_name = str(author)

        score = int(story.get("score", 0) or 0)
        comments = int(story.get("comments_count", 0) or 0)

        created_str = story.get("created_at", "")
        created_utc: datetime | None = None
        if created_str:
            try:
                created_utc = datetime.fromisoformat(
                    created_str.replace("Z", "+00:00")
                )
            except ValueError:
                created_utc = None

        tags_raw = story.get("tags", [])
        tags = [str(t) for t in tags_raw if t]

        return RawPost(
            url=story_url,
            url_hash=self._dedup_key(story_url),
            title=str(title),
            body=body,
            platform=self.platform,
            author=str(author_name),
            followers=0,
            author_karma=0,
            upvotes=score,
            score=score,
            comments=comments,
            comment_count=comments,
            tags=tags,
            scraped_at=datetime.utcnow(),
            created_utc=created_utc,
        )
