"""Batch-normalised signal scorer for OSS Radar posts."""

from __future__ import annotations

import math
from typing import List

from radar.models import PainCategory, RawPost, ScoredPost


class SignalScorer:
    """Converts a batch of RawPosts to ScoredPosts using log-normalised signals.

    Formula (from PRD FR-3.x):
        influence_norm  = log10(author_karma + 1) / log10(max_karma + 1)  clamped [0,1]
        engagement_norm = log10(score + comments + 1) / log10(max_eng + 1) clamped [0,1]
        base_score      = influence_weight * influence_norm + engagement_weight * engagement_norm
        pain_factor     = 1.0 (1 match) | 1.2 (2-3 matches) | 1.5 (4+ matches)
        maintainer_boost= 1.0 (1 signal) | 1.25 (2+ signals)
        signal_score    = base_score * pain_factor * (1.0 + abs(sentiment_score)) * maintainer_boost
    """

    def __init__(
        self,
        influence_weight: float = 0.4,
        engagement_weight: float = 0.6,
    ) -> None:
        self.influence_weight = influence_weight
        self.engagement_weight = engagement_weight

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score_batch(self, posts: List[RawPost]) -> List[ScoredPost]:
        """Score an entire batch; returns ScoredPosts sorted descending."""
        if not posts:
            return []

        karmas = [float(max(p.effective_followers(), 0)) for p in posts]
        engagements = [
            float(max(p.effective_upvotes() + p.effective_comments(), 0))
            for p in posts
        ]

        max_karma = max(karmas) if karmas else 0.0
        max_engagement = max(engagements) if engagements else 0.0

        scored: List[ScoredPost] = []
        for post, karma, eng in zip(posts, karmas, engagements):
            influence_norm = self._log10_norm(karma, max_karma)
            engagement_norm = self._log10_norm(eng, max_engagement)

            pain_factor = self._pain_factor(post)
            sentiment_factor = self._sentiment_factor(post)
            maintainer_boost = self._maintainer_boost(post)

            base_score = (
                self.influence_weight * influence_norm
                + self.engagement_weight * engagement_norm
            )
            final = base_score * pain_factor * sentiment_factor * maintainer_boost

            scored_post = ScoredPost(
                **post.model_dump(),
                influence_norm=round(influence_norm, 6),
                engagement_norm=round(engagement_norm, 6),
                pain_factor=round(pain_factor, 4),
                sentiment_factor=round(sentiment_factor, 4),
                maintainer_boost=maintainer_boost,
                final_score=round(final, 6),
                signal_score=round(final, 6),
            )
            scored.append(scored_post)

        scored.sort(key=lambda p: p.final_score, reverse=True)
        return scored

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _log10_norm(value: float, max_value: float) -> float:
        """log10(value + 1) / log10(max_value + 1), clamped [0, 1]."""
        if max_value <= 0:
            return 0.0
        denom = math.log10(max_value + 1)
        if denom == 0:
            return 0.0
        result = math.log10(value + 1) / denom
        return max(0.0, min(1.0, result))

    @staticmethod
    def _log1p_norm(value: float, max_value: float) -> float:
        """log1p(value) / log1p(max_value), clamped [0, 1]."""
        if max_value <= 0:
            return 0.0
        denom = math.log1p(max_value)
        if denom == 0:
            return 0.0
        result = math.log1p(value) / denom
        return max(0.0, min(1.0, result))

    @staticmethod
    def _pain_factor(post: RawPost) -> float:
        """1.0 for 1 keyword hit, 1.2 for 2–3 hits, 1.5 for 4+ hits."""
        n = len(post.pain_categories)
        if n >= 4:
            return 1.5
        if n >= 2:
            return 1.2
        return 1.0

    @staticmethod
    def _sentiment_factor(post: RawPost) -> float:
        """1.0 + abs(sentiment_score).  Sentiment is negative for pain posts."""
        raw = post.sentiment or post.raw_sentiment
        return 1.0 + abs(raw)

    @staticmethod
    def _maintainer_boost(post: RawPost) -> float:
        """1.0 for one maintainer signal, 1.25 for 2+ signals."""
        if not (post.is_maintainer or post.is_maintainer_context):
            return 1.0
        # Count distinct maintainer signals in title+body
        from radar.ranking.filters import MaintainerContextFilter

        ctx = MaintainerContextFilter()
        text = f"{post.title} {post.body}"
        n_signals = ctx.count_signals(text)
        return 1.25 if n_signals >= 2 else 1.0
