"""Hacker News scraper via Algolia Search API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from radar.config import Settings
from radar.models import RawPost
from radar.scraping.base import BaseScraper
from radar.scraping.http import SafeHTTPClient

logger = logging.getLogger(__name__)

_HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
_TAGS = ["ask_hn", "show_hn"]


class HNScraper(BaseScraper):
    """Fetches Ask HN and Show HN posts via Algolia HN Search API."""

    platform = "hackernews"

    def __init__(self, config: Settings, client: SafeHTTPClient | None = None) -> None:
        super().__init__(config, client)

    def fetch_raw(self) -> List[RawPost]:
        """Fetch recent posts for each HN tag type."""
        posts: List[RawPost] = []
        for tag in _TAGS:
            try:
                batch = self._fetch_tag(tag)
                posts.extend(batch)
            except Exception as exc:
                logger.warning(
                    "hn_tag_fetch_failed",
                    extra={"tag": tag, "error": str(exc)},
                )
        return posts

    def _fetch_tag(self, tag: str) -> List[RawPost]:
        """Fetch up to 25 posts for a single tag."""
        params = {
            "tags": tag,
            "hitsPerPage": 25,
        }
        response = self.client.get(_HN_SEARCH_URL, params=params)
        data = response.json()
        hits: List[Dict[str, Any]] = data.get("hits", [])
        return [self._hit_to_post(hit) for hit in hits]

    def _hit_to_post(self, hit: Dict[str, Any]) -> RawPost:
        """Convert an Algolia hit to a RawPost."""
        object_id = hit.get("objectID", "")
        url = hit.get("url", "") or f"https://news.ycombinator.com/item?id={object_id}"
        title = hit.get("title", "") or hit.get("story_title", "")
        body = hit.get("story_text", "") or hit.get("comment_text", "") or ""

        author = hit.get("author", "")
        points = int(hit.get("points", 0) or 0)
        num_comments = int(hit.get("num_comments", 0) or 0)

        created_str = hit.get("created_at", "")
        created_utc: datetime | None = None
        if created_str:
            try:
                created_utc = datetime.fromisoformat(
                    created_str.replace("Z", "+00:00")
                )
            except ValueError:
                created_utc = None

        tags_raw = hit.get("_tags", [])
        tags = [str(t) for t in tags_raw if t]

        return RawPost(
            url=url,
            url_hash=self._dedup_key(url),
            title=str(title),
            body=body,
            platform=self.platform,
            author=str(author),
            followers=0,
            author_karma=0,
            upvotes=points,
            score=points,
            comments=num_comments,
            comment_count=num_comments,
            tags=tags,
            scraped_at=datetime.utcnow(),
            created_utc=created_utc,
        )
