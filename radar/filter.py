"""SignalFilter — sealed-test-compatible filter facade for OSS Radar.

Works with plain post dicts (as produced by the sealed test conftest).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from radar.models import PainCategory
from radar.ranking.keywords import COMPILED_PATTERNS, MAINTAINER_PATTERNS, count_keyword_hits

# Re-export for patch targets used by sealed tests
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # type: ignore[import]
except ImportError:  # pragma: no cover
    SentimentIntensityAnalyzer = None  # type: ignore[assignment,misc]

try:
    from textblob import TextBlob  # type: ignore[import]
except ImportError:  # pragma: no cover
    TextBlob = None  # type: ignore[assignment,misc]

_VADER_WEIGHT = 0.6
_TEXTBLOB_WEIGHT = 0.4
_SENTIMENT_THRESHOLD = -0.05


class SignalFilter:
    """Three-layer filter that operates on plain post dicts."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def filter(self, posts: List[Dict]) -> List[Dict]:
        """Apply all three gates; return posts that pass every layer."""
        result = []
        for post in posts:
            if (
                self.passes_keyword_gate(post)
                and self.passes_maintainer_gate(post)
                and self.passes_sentiment_gate(post)
            ):
                result.append(post)
        return result

    # ------------------------------------------------------------------
    # Individual gates
    # ------------------------------------------------------------------

    def passes_keyword_gate(self, post: Dict) -> bool:
        """Return True if post matches at least one pain-category keyword."""
        text = f"{post.get('title', '')} {post.get('body', '')}"
        hits = count_keyword_hits(text)
        return bool(hits)

    def passes_maintainer_gate(self, post: Dict) -> bool:
        """Return True if post has maintainer context signals.

        Checks ``maintainer_signals`` list if present; falls back to
        regex scanning of title+body.
        """
        # If the dict explicitly provides maintainer_signals, use it
        signals = post.get("maintainer_signals")
        if signals is not None:
            if isinstance(signals, list):
                return len(signals) > 0
            return bool(signals)

        # Fall back to regex scanning
        text = f"{post.get('title', '')} {post.get('body', '')}"
        for pattern in MAINTAINER_PATTERNS:
            if pattern.search(text):
                return True
        return False

    def passes_sentiment_gate(self, post: Dict) -> bool:
        """Return True if post.sentiment_score < -0.05 (strictly)."""
        score = float(post.get("sentiment_score", 0.0))
        return score < _SENTIMENT_THRESHOLD

    # ------------------------------------------------------------------
    # Sentiment computation
    # ------------------------------------------------------------------

    def compute_sentiment(self, text: str) -> float:
        """Compute combined VADER+TextBlob sentiment for *text*.

        Uses module-level names so mock.patch works correctly.
        """
        vader_score = 0.0
        textblob_score = 0.0

        if SentimentIntensityAnalyzer is not None:
            analyzer = SentimentIntensityAnalyzer()
            vs = analyzer.polarity_scores(text)
            vader_score = vs["compound"]

        if TextBlob is not None:
            try:
                tb = TextBlob(text)
                textblob_score = tb.sentiment.polarity
            except Exception:
                textblob_score = 0.0

        return _VADER_WEIGHT * vader_score + _TEXTBLOB_WEIGHT * textblob_score
