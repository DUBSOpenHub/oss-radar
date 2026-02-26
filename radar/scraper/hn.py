"""Hacker News scraper — sealed-test-compatible."""

from __future__ import annotations

from typing import Dict, List

from radar.scraper.base import BaseScraper


class HNScraper(BaseScraper):
    platform = "hn"

    def _do_fetch(self) -> List[Dict]:
        return []
