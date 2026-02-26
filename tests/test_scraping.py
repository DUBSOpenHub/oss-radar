"""Tests for scraper modules — all external calls are mocked."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def settings(tmp_path):
    from radar.config import Settings
    return Settings(
        db_path=str(tmp_path / "test.db"),
        email_enabled=False,
        reddit_enabled=False,
    )


@pytest.fixture()
def mock_client():
    """Return a mock SafeHTTPClient."""
    client = MagicMock()
    return client


# ---------------------------------------------------------------------------
# HN Scraper tests
# ---------------------------------------------------------------------------


class TestHNScraper:
    def test_fetch_returns_raw_posts(self, settings, mock_client):
        from radar.scraping.hackernews import HNScraper

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "hits": [
                {
                    "objectID": "12345",
                    "title": "Ask HN: How do I deal with OSS burnout?",
                    "story_text": "I maintain several packages and I'm exhausted",
                    "author": "oss_dev",
                    "points": 150,
                    "num_comments": 42,
                    "created_at": "2024-01-15T10:00:00Z",
                    "_tags": ["ask_hn", "story"],
                    "url": "https://news.ycombinator.com/item?id=12345",
                }
            ]
        }
        mock_client.get.return_value = mock_response

        scraper = HNScraper(settings, mock_client)
        posts = scraper.fetch_raw()

        assert len(posts) > 0
        post = posts[0]
        assert post.platform == "hackernews"
        assert post.upvotes == 150
        assert post.comments == 42
        assert post.author == "oss_dev"

    def test_scrape_isolates_errors(self, settings, mock_client):
        from radar.scraping.hackernews import HNScraper

        mock_client.get.side_effect = Exception("Network error")
        scraper = HNScraper(settings, mock_client)
        posts = scraper.scrape()
        assert posts == []

    def test_hit_url_fallback(self, settings, mock_client):
        """When hit has no url, construct from objectID."""
        from radar.scraping.hackernews import HNScraper

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "hits": [
                {
                    "objectID": "99999",
                    "title": "Show HN: My project is struggling",
                    "author": "dev1",
                    "points": 10,
                    "num_comments": 5,
                    "created_at": "2024-01-10T08:00:00Z",
                    "_tags": ["show_hn"],
                    # No "url" key
                }
            ]
        }
        mock_client.get.return_value = mock_response
        scraper = HNScraper(settings, mock_client)
        posts = scraper.fetch_raw()
        assert len(posts) > 0
        assert "99999" in posts[0].url


# ---------------------------------------------------------------------------
# Dev.to Scraper tests
# ---------------------------------------------------------------------------


class TestDevToScraper:
    def test_fetch_returns_raw_posts(self, settings, mock_client):
        from radar.scraping.devto import DevToScraper

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "id": 1001,
                "title": "Why I Almost Quit OSS Maintenance",
                "description": "Burnout is real in open source",
                "url": "https://dev.to/user/oss-burnout",
                "canonical_url": "https://dev.to/user/oss-burnout",
                "user": {"username": "ossdev", "name": "OSS Dev"},
                "public_reactions_count": 200,
                "comments_count": 35,
                "published_at": "2024-01-15T10:00:00Z",
                "tag_list": ["opensource", "burnout"],
            }
        ]
        mock_client.get.return_value = mock_response

        scraper = DevToScraper(settings, mock_client)
        posts = scraper.fetch_raw()

        assert len(posts) > 0
        post = posts[0]
        assert post.platform == "devto"
        assert post.upvotes == 200
        assert post.comments == 35

    def test_dedup_across_tags(self, settings, mock_client):
        """Same article fetched for multiple tags is only included once."""
        from radar.scraping.devto import DevToScraper

        same_article = {
            "id": 9999,
            "title": "Duplicate Article",
            "description": "body",
            "url": "https://dev.to/user/duplicate",
            "user": {"username": "u"},
            "public_reactions_count": 10,
            "comments_count": 2,
            "published_at": "2024-01-10T00:00:00Z",
            "tag_list": [],
        }
        mock_response = MagicMock()
        mock_response.json.return_value = [same_article]
        mock_client.get.return_value = mock_response

        scraper = DevToScraper(settings, mock_client)
        posts = scraper.fetch_raw()
        urls = [p.url for p in posts]
        assert len(urls) == len(set(urls))

    def test_scrape_isolates_errors(self, settings, mock_client):
        from radar.scraping.devto import DevToScraper

        mock_client.get.side_effect = Exception("API error")
        scraper = DevToScraper(settings, mock_client)
        posts = scraper.scrape()
        assert posts == []


# ---------------------------------------------------------------------------
# Lobsters Scraper tests
# ---------------------------------------------------------------------------


class TestLobstersScraper:
    def test_fetch_returns_raw_posts(self, settings, mock_client):
        from radar.scraping.lobsters import LobstersScraper

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "title": "OSS Maintainer Burnout Is Real",
                "url": "https://example.com/burnout",
                "short_id_url": "https://lobste.rs/s/abc123",
                "submitter_user": {"username": "lobster_user"},
                "score": 45,
                "comments_count": 12,
                "created_at": "2024-01-15T09:00:00Z",
                "tags": ["programming", "oss"],
                "description": "A tale of CI failing forever",
            }
        ]
        mock_client.get.return_value = mock_response

        scraper = LobstersScraper(settings, mock_client)
        posts = scraper.fetch_raw()

        assert len(posts) > 0
        post = posts[0]
        assert post.platform == "lobsters"
        assert post.upvotes == 45

    def test_scrape_isolates_errors(self, settings, mock_client):
        from radar.scraping.lobsters import LobstersScraper

        mock_client.get.side_effect = Exception("Feed error")
        scraper = LobstersScraper(settings, mock_client)
        posts = scraper.scrape()
        assert posts == []


# ---------------------------------------------------------------------------
# BaseScraper contract tests
# ---------------------------------------------------------------------------


class TestBaseScraper:
    def test_dedup_key_is_sha256(self):
        """_dedup_key returns a 64-char hex string."""
        from radar.scraping.hackernews import HNScraper
        from radar.config import Settings

        settings = Settings(email_enabled=False, reddit_enabled=False)
        scraper = HNScraper(settings)
        key = scraper._dedup_key("https://example.com/post")
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_dedup_key_normalizes_trailing_slash(self):
        from radar.scraping.hackernews import HNScraper
        from radar.config import Settings

        settings = Settings(email_enabled=False, reddit_enabled=False)
        scraper = HNScraper(settings)
        key1 = scraper._dedup_key("https://example.com/post/")
        key2 = scraper._dedup_key("https://example.com/post")
        assert key1 == key2

    def test_scrape_returns_list_on_exception(self):
        from radar.scraping.hackernews import HNScraper
        from radar.config import Settings

        settings = Settings(email_enabled=False, reddit_enabled=False)
        scraper = HNScraper(settings)
        # Patch fetch_raw to raise
        scraper.fetch_raw = lambda: (_ for _ in ()).throw(Exception("boom"))  # type: ignore[assignment]
        result = scraper.scrape()
        assert result == []
