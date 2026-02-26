"""LLM Backend — GitHub Models API primary, Amplifier CLI fallback.

Ported from DUBSOpenHub/ghost-ops. Pure Python stdlib — no new pip deps.
Uses `gh api` for GitHub Models and `uv run amplifier` as fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, List

logger = logging.getLogger(__name__)

_STUB_RESPONSE = {
    "content": "[DRY-RUN] No LLM call made.",
    "model": "stub",
    "tokens_in": 0,
    "tokens_out": 0,
}


@dataclass
class LLMResponse:
    """Structured response from any LLM backend."""

    content: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


class LLMBackend:
    """Wraps GitHub Models API and Amplifier CLI with dry-run support.

    Primary: GitHub Models API via ``gh api /models/chat/completions``
    Fallback: Amplifier CLI via ``uv run amplifier``
    """

    def __init__(
        self,
        default_model: str = "claude-sonnet-4.6",
        dry_run: bool = False,
    ) -> None:
        self.default_model = default_model
        self.dry_run = dry_run

    async def complete(
        self,
        messages: List[dict[str, str]],
        model: str | None = None,
        *,
        max_tokens: int = 256,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """Run a chat completion, returning LLMResponse."""
        if self.dry_run:
            return LLMResponse(**_STUB_RESPONSE)

        target_model = model or self.default_model
        errors: list[str] = []

        # Primary: GitHub Models
        try:
            return await self._github_models(messages, target_model, max_tokens, temperature)
        except Exception as exc:
            errors.append(f"github-models: {exc}")
            logger.warning("Primary LLM failed (%s), trying Amplifier fallback", exc)

        # Fallback: Amplifier
        try:
            return await self._amplifier(messages, target_model)
        except Exception as exc:
            errors.append(f"amplifier: {exc}")
            logger.error("All LLM backends failed: %s", "; ".join(errors))
            raise RuntimeError(f"All LLM backends failed: {'; '.join(errors)}") from exc

    def complete_sync(
        self,
        messages: List[dict[str, str]],
        model: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Synchronous wrapper around complete() for pipeline use."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already in an async context — create a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self.complete(messages, model, **kwargs))
                return future.result(timeout=120)
        else:
            return asyncio.run(self.complete(messages, model, **kwargs))

    # ------------------------------------------------------------------
    # GitHub Models via `gh api`
    # ------------------------------------------------------------------

    async def _github_models(
        self,
        messages: List[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        payload = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        proc = await asyncio.create_subprocess_exec(
            "gh", "api",
            "--method", "POST",
            "-H", "Accept: application/vnd.github+json",
            "/models/chat/completions",
            "--input", "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=payload.encode()), timeout=60,
        )

        if proc.returncode != 0:
            raise RuntimeError(f"gh api exit {proc.returncode}: {stderr.decode().strip()}")

        data = json.loads(stdout.decode())
        choice = data["choices"][0]["message"]
        usage = data.get("usage", {})
        return LLMResponse(
            content=choice.get("content", ""),
            model=data.get("model", model),
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
            raw=data,
        )

    # ------------------------------------------------------------------
    # Amplifier CLI fallback
    # ------------------------------------------------------------------

    async def _amplifier(
        self,
        messages: List[dict[str, str]],
        model: str,
    ) -> LLMResponse:
        prompt_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in messages
        )
        amplifier_dir = os.path.expanduser("~/amplifier")
        proc = await asyncio.create_subprocess_exec(
            "uv", "run", "amplifier",
            "--model", model,
            "--",
            prompt_text,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=amplifier_dir,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            raise RuntimeError(f"amplifier exit {proc.returncode}: {stderr.decode().strip()}")

        content = stdout.decode().strip()
        return LLMResponse(content=content, model=model)
