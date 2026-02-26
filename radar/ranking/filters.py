"""Three-layer filter pipeline for OSS Radar signal detection."""

from __future__ import annotations

import re
from typing import List

from radar.models import PainCategory, RawPost
from radar.ranking.keywords import (
    COMPILED_PATTERNS,
    MAINTAINER_PATTERNS,
    count_keyword_hits,
)

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # type: ignore[import]

    _VADER_AVAILABLE = True
except ImportError:  # pragma: no cover
    _VADER_AVAILABLE = False

try:
    from textblob import TextBlob  # type: ignore[import]

    _TEXTBLOB_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TEXTBLOB_AVAILABLE = False


class KeywordFilter:
    """Layer 1: keep posts matching ≥1 keyword across all PainCategories.

    Populates ``post.pain_categories`` and ``post.pain_score`` as a side effect.
    """

    def __init__(self) -> None:
        self._patterns = COMPILED_PATTERNS

    def apply(self, posts: List[RawPost]) -> List[RawPost]:
        """Return posts that match at least one keyword; enrich with categories."""
        passing: List[RawPost] = []
        for post in posts:
            text = f"{post.title} {post.body}"
            hits = count_keyword_hits(text)
            if hits:
                post.pain_categories = list(hits.keys())
                post.pain_score = sum(hits.values())
                passing.append(post)
        return passing

    def _score_categories(self, text: str) -> dict[PainCategory, float]:
        """Return per-category weighted hit counts."""
        return count_keyword_hits(text)


class MaintainerContextFilter:
    """Layer 2: keep posts that contain ≥1 maintainer-context signal."""

    def __init__(self) -> None:
        self._patterns: List[re.Pattern[str]] = MAINTAINER_PATTERNS

    def apply(self, posts: List[RawPost]) -> List[RawPost]:
        """Return posts where the author demonstrates maintainer context."""
        passing: List[RawPost] = []
        for post in posts:
            if self._is_maintainer(post):
                post.is_maintainer = True
                post.is_maintainer_context = True
                passing.append(post)
        return passing

    def _is_maintainer(self, post: RawPost) -> bool:
        """Return True if post contains ≥1 maintainer-context pattern."""
        text = f"{post.title} {post.body}"
        for pattern in self._patterns:
            if pattern.search(text):
                return True
        # Also check if author username appears in a GitHub URL within the post
        if post.author:
            github_pattern = re.compile(
                rf"github\.com/{re.escape(post.author)}/",
                re.IGNORECASE,
            )
            if github_pattern.search(text):
                return True
        return False

    def count_signals(self, text: str) -> int:
        """Return how many distinct maintainer signals are present."""
        count = 0
        for pattern in self._patterns:
            if pattern.search(text):
                count += 1
        return count


class SentimentFilter:
    """Layer 3: keep only pain-signal posts (negative sentiment).

    Combined score = VADER_compound × vader_weight + TextBlob_polarity × textblob_weight
    Post passes only when combined_score < −0.05.
    """

    PASS_THRESHOLD = -0.05

    def __init__(
        self,
        vader_weight: float = 0.6,
        textblob_weight: float = 0.4,
    ) -> None:
        self.vader_weight = vader_weight
        self.textblob_weight = textblob_weight
        self._vader: object = None
        if _VADER_AVAILABLE:
            self._vader = SentimentIntensityAnalyzer()  # type: ignore[assignment]

    def apply(self, posts: List[RawPost]) -> List[RawPost]:
        """Return posts with combined sentiment < −0.05; store score on post."""
        passing: List[RawPost] = []
        for post in posts:
            text = f"{post.title} {post.body}"
            score = self._combined_score(text)
            post.sentiment = score
            post.raw_sentiment = score
            if score < self.PASS_THRESHOLD:
                passing.append(post)
        return passing

    def _combined_score(self, text: str) -> float:
        """Return combined VADER+TextBlob sentiment score.

        Range is approximately [-1, +1].  Negative values indicate pain.
        """
        vader_score = 0.0
        textblob_score = 0.0

        if _VADER_AVAILABLE and self._vader is not None:
            vs = self._vader.polarity_scores(text)  # type: ignore[attr-defined]
            vader_score = vs["compound"]
        if _TEXTBLOB_AVAILABLE:
            try:
                tb = TextBlob(text)
                textblob_score = tb.sentiment.polarity
            except Exception:
                textblob_score = 0.0

        return self.vader_weight * vader_score + self.textblob_weight * textblob_score


class FilterPipeline:
    """Composes all three filter layers sequentially.

    All three layers must pass for a post to reach the scorer.
    """

    def __init__(
        self,
        vader_weight: float = 0.6,
        textblob_weight: float = 0.4,
    ) -> None:
        self.keyword_filter = KeywordFilter()
        self.maintainer_filter = MaintainerContextFilter()
        self.sentiment_filter = SentimentFilter(
            vader_weight=vader_weight,
            textblob_weight=textblob_weight,
        )

    def apply(self, posts: List[RawPost]) -> List[RawPost]:
        """Run all three layers; return posts passing every layer."""
        after_kw = self.keyword_filter.apply(posts)
        after_mc = self.maintainer_filter.apply(after_kw)
        after_sent = self.sentiment_filter.apply(after_mc)
        return after_sent
