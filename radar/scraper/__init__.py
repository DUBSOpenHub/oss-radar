"""radar.scraper — unified scraper package."""

from __future__ import annotations

import logging
from typing import Dict, List

from radar.scraper.base import BaseScraper, SSRFGuard, SSRFError
from radar.scraper.devto import DevToScraper
from radar.scraper.hn import HNScraper
from radar.scraper.lobsters import LobstersScraper
from radar.scraper.reddit import RedditScraper

logger = logging.getLogger(__name__)

__all__ = [
    "ScraperManager",
    "SSRFGuard",
    "SSRFError",
    "BaseScraper",
    "RedditScraper",
    "HNScraper",
    "DevToScraper",
    "LobstersScraper",
]


class ScraperManager:
    """Run all platform scrapers; isolate failures."""

    def __init__(self) -> None:
        self._scrapers: List[BaseScraper] = [
            RedditScraper(),
            HNScraper(),
            DevToScraper(),
            LobstersScraper(),
        ]

    def fetch_all(self) -> List[Dict]:
        """Run every scraper; combine results; isolate per-scraper failures."""
        combined: List[Dict] = []
        for scraper in self._scrapers:
            try:
                posts = scraper.fetch()
                combined.extend(posts)
            except Exception as exc:
                logger.error("scraper_failed", extra={"platform": scraper.platform, "error": str(exc)})
        return combined
