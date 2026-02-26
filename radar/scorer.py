"""SignalScorer — sealed-test-compatible scorer that works with plain dicts."""

from __future__ import annotations

import math
from typing import Dict, List


class SignalScorer:
    """Log-scale batch scorer for plain post dicts.

    Uses ``score`` as the influence signal and ``num_comments`` as
    the engagement signal, mirroring the sealed-test contract.
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

    def rank(self, posts: List[Dict]) -> List[Dict]:
        """Score and sort *posts* (plain dicts); return list with ``signal_score``."""
        if not posts:
            return []

        scores = [float(max(p.get("score", 0) or 0, 0)) for p in posts]
        comments = [float(max(p.get("num_comments", 0) or 0, 0)) for p in posts]
        sentiments = [float(p.get("sentiment_score", 0.0) or 0.0) for p in posts]
        maintainer_lists = [p.get("maintainer_signals") or [] for p in posts]

        max_score = max(scores) if scores else 0.0
        max_comments = max(comments) if comments else 0.0

        raw_scores = []
        for s, c, sent, msigs in zip(scores, comments, sentiments, maintainer_lists):
            influence_norm = self._log10_norm(s, max_score)
            engagement_norm = self._log10_norm(c, max_comments)

            base = (
                self.influence_weight * influence_norm
                + self.engagement_weight * engagement_norm
            )

            sentiment_factor = 1.0 + abs(sent)

            n_signals = len(msigs) if isinstance(msigs, list) else 0
            maintainer_boost = 1.25 if n_signals >= 2 else 1.0

            raw_scores.append(base * sentiment_factor * maintainer_boost)

        # Batch-normalise to [0, 1]
        max_raw = max(raw_scores) if raw_scores else 0.0

        result = []
        for post, raw in zip(posts, raw_scores):
            if max_raw > 0:
                normalised = raw / max_raw
            else:
                normalised = 0.0
            new_post = dict(post)
            new_post["signal_score"] = max(0.0, min(1.0, normalised))
            result.append(new_post)

        result.sort(key=lambda p: p["signal_score"], reverse=True)
        return result

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
