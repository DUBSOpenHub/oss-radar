"""Reddit scraper — sealed-test-compatible."""

from __future__ import annotations

from typing import Dict, List

from radar.scraper.base import BaseScraper


class RedditScraper(BaseScraper):
    platform = "reddit"

    def _do_fetch(self) -> List[Dict]:
        return []
