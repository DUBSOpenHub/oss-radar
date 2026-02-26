"""Reddit scraper using PRAW."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from radar.config import Settings
from radar.models import RawPost
from radar.scraping.base import BaseScraper
from radar.scraping.http import SafeHTTPClient

logger = logging.getLogger(__name__)

_SUBREDDITS_DEFAULT = [
    "opensource",
    "programming",
    "devops",
    "Python",
    "rust",
    "golang",
    "netsec",
    "MachineLearning",
]


class RedditScraper(BaseScraper):
    """Fetches top posts from configured subreddits via PRAW."""

    platform = "reddit"

    def __init__(self, config: Settings, client: SafeHTTPClient | None = None) -> None:
        super().__init__(config, client)
        self._subreddits = config.reddit_subreddits or _SUBREDDITS_DEFAULT

    def fetch_raw(self) -> List[RawPost]:
        """Fetch posts from all configured subreddits."""
        if not self.config.reddit_enabled:
            logger.info("reddit_scraper_disabled")
            return []

        try:
            import praw  # type: ignore[import]
        except ImportError:
            logger.warning("praw_not_installed; skipping Reddit scraper")
            return []

        reddit = praw.Reddit(
            client_id=self.config.reddit_client_id,
            client_secret=self.config.reddit_client_secret,
            user_agent=self.config.reddit_user_agent,
        )

        posts: List[RawPost] = []
        for sub_name in self._subreddits:
            try:
                subreddit = reddit.subreddit(sub_name)
                for submission in subreddit.new(limit=25):
                    try:
                        post = self._submission_to_post(submission)
                        posts.append(post)
                    except Exception as exc:
                        logger.debug(
                            "reddit_post_parse_error",
                            extra={"sub": sub_name, "error": str(exc)},
                        )
            except Exception as exc:
                logger.warning(
                    "reddit_subreddit_failed",
                    extra={"sub": sub_name, "error": str(exc)},
                )

        return posts

    def _submission_to_post(self, submission: object) -> RawPost:
        """Convert a PRAW submission to a RawPost."""
        url = getattr(submission, "url", "")
        permalink = getattr(submission, "permalink", "")
        if permalink:
            url = f"https://www.reddit.com{permalink}"

        body = getattr(submission, "selftext", "") or ""
        author_obj = getattr(submission, "author", None)
        author_name = str(getattr(author_obj, "name", "")) if author_obj else ""
        author_karma = 0
        if author_obj:
            try:
                author_karma = int(getattr(author_obj, "link_karma", 0))
            except Exception:
                author_karma = 0

        created_ts = getattr(submission, "created_utc", 0)
        created_at = datetime.fromtimestamp(float(created_ts), tz=timezone.utc)

        flair = getattr(submission, "link_flair_text", "") or ""
        tags = [flair] if flair else []

        return RawPost(
            url=url,
            url_hash=self._dedup_key(url),
            title=str(getattr(submission, "title", "")),
            body=body,
            platform=self.platform,
            author=author_name,
            followers=author_karma,
            author_karma=author_karma,
            upvotes=int(getattr(submission, "score", 0)),
            score=int(getattr(submission, "score", 0)),
            comments=int(getattr(submission, "num_comments", 0)),
            comment_count=int(getattr(submission, "num_comments", 0)),
            tags=tags,
            scraped_at=datetime.utcnow(),
            created_utc=created_at,
        )
