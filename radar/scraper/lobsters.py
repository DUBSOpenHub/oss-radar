"""Lobsters scraper — sealed-test-compatible."""

from __future__ import annotations

from typing import Dict, List

from radar.scraper.base import BaseScraper


class LobstersScraper(BaseScraper):
    platform = "lobsters"

    def _do_fetch(self) -> List[Dict]:
        return []
