"""Pain-point summarizer — LLM-powered one-sentence summaries.

Uses LLMBackend to generate concise summaries of each scored post.
Graceful degradation: if LLM fails, falls back to 120-char body excerpt.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from radar.llm import LLMBackend

if TYPE_CHECKING:
    from radar.models import ScoredPost

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Summarize this open source maintainer's pain point in one sentence. "
    "Be specific about the technical problem. No generic platitudes. "
    "Max 120 characters."
)


def _excerpt(body: str | None, max_len: int = 120) -> str:
    """Extract a plain-text excerpt from body text."""
    if not body:
        return ""
    text = body.strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rsplit(" ", 1)[0] + "..."


def summarize_posts(
    posts: List[ScoredPost],
    *,
    model: str | None = None,
    dry_run: bool = False,
) -> List[ScoredPost]:
    """Add LLM-generated summaries to each scored post.

    On LLM failure for any individual post, falls back to a body excerpt.
    """
    backend = LLMBackend(dry_run=dry_run)
    successes = 0

    for post in posts:
        user_text = f"Title: {post.title}\n\nBody: {(post.body or '')[:1000]}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]
        try:
            resp = backend.complete_sync(messages, model=model, max_tokens=100)
            post.llm_summary = resp.content.strip()
            successes += 1
        except Exception as exc:
            logger.warning(
                "LLM summary failed for post %s, using excerpt: %s",
                getattr(post, "url", "?"),
                exc,
            )
            post.llm_summary = _excerpt(post.body)

    logger.info(
        "Summarized %d/%d posts via LLM",
        successes,
        len(posts),
    )
    return posts
