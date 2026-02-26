"""FallbackLadder — live → archive-7d → archive-30d → partial."""

from __future__ import annotations

from typing import Dict, List, Optional

from radar.db import CatalogDB
from radar.scraper import ScraperManager
from radar.filter import SignalFilter


class FallbackLadder:
    """Implements the exactly-5 post fallback ladder."""

    TARGET = 5

    def __init__(self, db: CatalogDB) -> None:
        self.db = db

    def get_five(self) -> List[Dict]:
        """Return up to 5 posts following the fallback ladder."""
        result = list(self._fetch_live())

        if len(result) >= self.TARGET:
            for p in result:
                p.setdefault("source_tier", "live")
            return result[:self.TARGET]

        # Rung 2 — archive-7d
        archive_7d = self._fetch_archive_7d()
        for p in archive_7d:
            p.setdefault("source_tier", "archive-7d")
        result.extend(archive_7d)

        if len(result) >= self.TARGET:
            return result[:self.TARGET]

        # Rung 3 — archive-30d
        archive_30d = self._fetch_archive_30d()
        for p in archive_30d:
            p.setdefault("source_tier", "archive-30d")
        existing_urls = {p.get("url") for p in result}
        for p in archive_30d:
            if p.get("url") not in existing_urls:
                result.append(p)
                existing_urls.add(p.get("url"))
                if len(result) >= self.TARGET:
                    break

        if len(result) >= self.TARGET:
            return result[:self.TARGET]

        # Still < TARGET — mark posts whose tier is still "live" as "partial"
        # (posts already tagged with "archive-*" keep their tier)
        for p in result:
            if p.get("source_tier") == "live" or p.get("source_tier") not in {
                "live", "archive-7d", "archive-30d"
            }:
                p["source_tier"] = "partial"

        return result

    # ------------------------------------------------------------------
    # Overridable tier fetchers
    # ------------------------------------------------------------------

    def _fetch_live(self) -> List[Dict]:
        """Fetch live posts via ScraperManager + SignalFilter."""
        try:
            manager = ScraperManager()
            posts = manager.fetch_all()
            filt = SignalFilter()
            return filt.filter(posts)
        except Exception:
            return []

    def _fetch_archive_7d(self) -> List[Dict]:
        """Fetch unreported posts from the last 7 days."""
        return []

    def _fetch_archive_30d(self) -> List[Dict]:
        """Fetch unreported posts from the last 30 days."""
        return []
