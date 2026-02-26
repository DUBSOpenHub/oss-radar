"""Dev.to REST API scraper."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

from radar.config import Settings
from radar.models import RawPost
from radar.scraping.base import BaseScraper
from radar.scraping.http import SafeHTTPClient

logger = logging.getLogger(__name__)

_DEVTO_API = "https://dev.to/api/articles"
_TAGS = ["opensource", "devops", "python", "github"]


class DevToScraper(BaseScraper):
    """Fetches articles from Dev.to public REST API."""

    platform = "devto"

    def __init__(self, config: Settings, client: SafeHTTPClient | None = None) -> None:
        super().__init__(config, client)

    def fetch_raw(self) -> List[RawPost]:
        """Fetch articles for each configured tag."""
        posts: List[RawPost] = []
        seen_ids: set[str] = set()
        for tag in _TAGS:
            try:
                batch = self._fetch_tag(tag)
                for post in batch:
                    if post.url_hash not in seen_ids:
                        seen_ids.add(post.url_hash)
                        posts.append(post)
            except Exception as exc:
                logger.warning(
                    "devto_tag_fetch_failed",
                    extra={"tag": tag, "error": str(exc)},
                )
        return posts

    def _fetch_tag(self, tag: str) -> List[RawPost]:
        """Fetch up to 20 articles for a single tag."""
        params = {
            "tag": tag,
            "per_page": 20,
            "top": 1,
        }
        response = self.client.get(_DEVTO_API, params=params)
        articles: List[Dict[str, Any]] = response.json()
        return [self._article_to_post(a) for a in articles]

    def _article_to_post(self, article: Dict[str, Any]) -> RawPost:
        """Convert a Dev.to article JSON object to a RawPost."""
        url = article.get("url", "") or article.get("canonical_url", "")
        title = article.get("title", "")
        body = article.get("description", "") or article.get("body_markdown", "") or ""

        user = article.get("user", {}) or {}
        author = user.get("username", "") or user.get("name", "")

        reactions = int(article.get("public_reactions_count", 0) or 0)
        comments = int(article.get("comments_count", 0) or 0)

        published_str = article.get("published_at", "")
        created_utc: datetime | None = None
        if published_str:
            try:
                created_utc = datetime.fromisoformat(
                    published_str.replace("Z", "+00:00")
                )
            except ValueError:
                created_utc = None

        tag_list_raw = article.get("tag_list", [])
        if isinstance(tag_list_raw, str):
            tag_list = [t.strip() for t in tag_list_raw.split(",") if t.strip()]
        else:
            tag_list = list(tag_list_raw)

        return RawPost(
            url=url,
            url_hash=self._dedup_key(url),
            title=str(title),
            body=body,
            platform=self.platform,
            author=str(author),
            followers=0,
            author_karma=0,
            upvotes=reactions,
            score=reactions,
            comments=comments,
            comment_count=comments,
            tags=tag_list,
            scraped_at=datetime.utcnow(),
            created_utc=created_utc,
        )
