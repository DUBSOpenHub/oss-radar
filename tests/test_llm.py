"""Tests for LLM backend and summarizer modules."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from radar.llm import LLMBackend, LLMResponse
from radar.summarizer import _excerpt, summarize_posts


# ---------------------------------------------------------------------------
# LLMResponse tests
# ---------------------------------------------------------------------------


class TestLLMResponse:
    def test_basic_fields(self):
        r = LLMResponse(content="hello", model="test-model")
        assert r.content == "hello"
        assert r.model == "test-model"
        assert r.tokens_in == 0
        assert r.tokens_out == 0

    def test_with_usage(self):
        r = LLMResponse(content="x", model="m", tokens_in=10, tokens_out=5)
        assert r.tokens_in == 10
        assert r.tokens_out == 5


# ---------------------------------------------------------------------------
# LLMBackend tests
# ---------------------------------------------------------------------------


class TestLLMBackendDryRun:
    def test_dry_run_returns_stub(self):
        backend = LLMBackend(dry_run=True)
        result = backend.complete_sync([{"role": "user", "content": "test"}])
        assert result.content == "[DRY-RUN] No LLM call made."
        assert result.model == "stub"
        assert result.tokens_in == 0

    def test_dry_run_async(self):
        backend = LLMBackend(dry_run=True)
        result = asyncio.run(
            backend.complete([{"role": "user", "content": "test"}])
        )
        assert result.content == "[DRY-RUN] No LLM call made."


class TestLLMBackendGitHubModels:
    @patch("asyncio.create_subprocess_exec")
    def test_github_models_success(self, mock_exec):
        api_response = {
            "choices": [{"message": {"content": "Summary here"}}],
            "model": "test-model",
            "usage": {"prompt_tokens": 50, "completion_tokens": 20},
        }
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            json.dumps(api_response).encode(),
            b"",
        )
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        backend = LLMBackend()
        result = backend.complete_sync([{"role": "user", "content": "test"}])
        assert result.content == "Summary here"
        assert result.tokens_in == 50
        assert result.tokens_out == 20

    @patch("asyncio.create_subprocess_exec")
    def test_github_models_failure_falls_to_amplifier(self, mock_exec):
        # First call (gh api) fails, second call (amplifier) succeeds
        gh_proc = AsyncMock()
        gh_proc.communicate.return_value = (b"", b"auth error")
        gh_proc.returncode = 1

        amp_proc = AsyncMock()
        amp_proc.communicate.return_value = (b"Amplifier summary", b"")
        amp_proc.returncode = 0

        mock_exec.side_effect = [gh_proc, amp_proc]

        backend = LLMBackend()
        result = backend.complete_sync([{"role": "user", "content": "test"}])
        assert result.content == "Amplifier summary"

    @patch("asyncio.create_subprocess_exec")
    def test_all_backends_fail_raises(self, mock_exec):
        proc = AsyncMock()
        proc.communicate.return_value = (b"", b"error")
        proc.returncode = 1
        mock_exec.return_value = proc

        backend = LLMBackend()
        with pytest.raises(RuntimeError, match="All LLM backends failed"):
            backend.complete_sync([{"role": "user", "content": "test"}])


# ---------------------------------------------------------------------------
# Excerpt helper tests
# ---------------------------------------------------------------------------


class TestExcerpt:
    def test_empty_body(self):
        assert _excerpt(None) == ""
        assert _excerpt("") == ""

    def test_short_body(self):
        assert _excerpt("Hello world") == "Hello world"

    def test_truncation(self):
        long_text = "word " * 50
        result = _excerpt(long_text, max_len=120)
        assert len(result) <= 120
        assert result.endswith("...")

    def test_newlines_stripped(self):
        assert "\n" not in _excerpt("line1\nline2\nline3")


# ---------------------------------------------------------------------------
# Summarizer tests
# ---------------------------------------------------------------------------


class TestSummarizePosts:
    def _make_post(self, title="Test Post", body="Test body text"):
        from radar.models import ScoredPost

        return ScoredPost(
            url="https://example.com/1",
            title=title,
            body=body,
            platform="hackernews",
        )

    def test_dry_run_adds_stub_summary(self):
        posts = [self._make_post()]
        result = summarize_posts(posts, dry_run=True)
        assert len(result) == 1
        assert result[0].llm_summary == "[DRY-RUN] No LLM call made."

    @patch("radar.summarizer.LLMBackend")
    def test_llm_failure_falls_back_to_excerpt(self, MockBackend):
        instance = MockBackend.return_value
        instance.complete_sync.side_effect = RuntimeError("fail")

        post = self._make_post(body="A" * 200)
        result = summarize_posts([post])
        assert len(result) == 1
        # Falls back to excerpt
        assert result[0].llm_summary != ""
        assert len(result[0].llm_summary) <= 120

    @patch("radar.summarizer.LLMBackend")
    def test_successful_summary(self, MockBackend):
        instance = MockBackend.return_value
        instance.complete_sync.return_value = LLMResponse(
            content="Maintainer struggles with CI/CD pipeline reliability.",
            model="test",
        )

        post = self._make_post()
        result = summarize_posts([post])
        assert result[0].llm_summary == "Maintainer struggles with CI/CD pipeline reliability."

    @patch("radar.summarizer.LLMBackend")
    def test_multiple_posts_partial_failure(self, MockBackend):
        instance = MockBackend.return_value
        instance.complete_sync.side_effect = [
            LLMResponse(content="Good summary", model="test"),
            RuntimeError("fail"),
        ]

        posts = [self._make_post(), self._make_post(body="B" * 200)]
        result = summarize_posts(posts)
        assert result[0].llm_summary == "Good summary"
        assert result[1].llm_summary != ""  # excerpt fallback
        assert len(result[1].llm_summary) <= 120

    def test_empty_posts_list(self):
        result = summarize_posts([], dry_run=True)
        assert result == []


# ---------------------------------------------------------------------------
# Config LLM fields tests
# ---------------------------------------------------------------------------


class TestConfigLLMFields:
    def test_llm_defaults(self):
        from radar.config import Settings

        s = Settings()
        assert s.llm_enabled is False
        assert s.llm_model == "claude-sonnet-4.6"

    def test_llm_enabled_via_env(self, monkeypatch):
        from radar.config import Settings

        monkeypatch.setenv("RADAR_LLM_ENABLED", "true")
        monkeypatch.setenv("RADAR_LLM_MODEL", "gpt-4o")
        s = Settings()
        assert s.llm_enabled is True
        assert s.llm_model == "gpt-4o"


# ---------------------------------------------------------------------------
# Model llm_summary field tests
# ---------------------------------------------------------------------------


class TestScoredPostLLMSummary:
    def test_default_empty(self):
        from radar.models import ScoredPost

        p = ScoredPost(url="https://example.com", title="Test", platform="hn")
        assert p.llm_summary == ""

    def test_set_summary(self):
        from radar.models import ScoredPost

        p = ScoredPost(
            url="https://example.com",
            title="Test",
            platform="hn",
            llm_summary="Pain point summary",
        )
        assert p.llm_summary == "Pain point summary"
