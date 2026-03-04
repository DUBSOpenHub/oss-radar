# Code Review: Sentiment Scoring and Ranking Analysis
**Task:** Review `radar/ranking/filters.py` (SentimentFilter) and `radar/ranking/scorer.py` for scoring accuracy, normalization logic, and edge cases.

**Date:** 2026-03-04  
**Reviewer:** Stampede Agent  
**Status:** Complete

---

## Overview

Reviewed 307 lines across two critical scoring modules:
- `radar/ranking/filters.py` (174 lines) — Three-layer filter pipeline with sentiment scoring
- `radar/ranking/scorer.py` (133 lines) — Log-normalized batch scoring and ranking

All 21 unit tests pass. Identified 7 issues: 1 HIGH, 2 MEDIUM, 4 LOW.

---

## Critical Issues

### 1. **Unbounded Sentiment Amplification in `_sentiment_factor()` [HIGH]**

**Location:** `radar/ranking/scorer.py:116-119`

**Code:**
```python
@staticmethod
def _sentiment_factor(post: RawPost) -> float:
    """1.0 + abs(sentiment_score).  Sentiment is negative for pain posts."""
    raw = post.sentiment or post.raw_sentiment
    return 1.0 + abs(raw)
```

**Problem:**
- Sentiment values range approximately [-1, +1] from VADER+TextBlob blend
- Factor formula `1.0 + abs(raw)` produces range [1.0, 2.0]
- For extreme sentiment (-0.95), amplification is ~1.95x — works but lacks safety guard
- **No clamping** if sentiment accidentally exceeds [-1, +1]
- **No validation** that `raw` is not None when both fields are None/0

**Impact:**  
If sentiment normalization changes or external sources provide unbounded sentiment scores, final ranking could spike unpredictably.

**Recommendation:**
```python
@staticmethod
def _sentiment_factor(post: RawPost) -> float:
    """1.0 + abs(sentiment_score), clamped to [1.0, 2.0].
    
    Sentiment is negative for pain posts. Range is [-1, +1].
    """
    raw = post.sentiment if post.sentiment != 0.0 else post.raw_sentiment
    if raw is None:
        return 1.0
    clamped = max(-1.0, min(1.0, raw))
    return 1.0 + abs(clamped)
```

---

### 2. **Sentiment Score Mutation on Filtered-Out Posts [MEDIUM]**

**Location:** `radar/ranking/filters.py:117-127`

**Code:**
```python
def apply(self, posts: List[RawPost]) -> List[RawPost]:
    """Return posts with combined sentiment < −0.05; store score on post."""
    passing: List[RawPost] = []
    for post in posts:
        text = f"{post.title} {post.body}"
        score = self._combined_score(text)
        post.sentiment = score        # ← MUTATION
        post.raw_sentiment = score    # ← MUTATION
        if score < self.PASS_THRESHOLD:
            passing.append(post)
    return passing
```

**Problem:**
- **Side effect:** ALL posts have sentiment computed and stored, but only passing posts are returned
- **Inconsistent state:** If pipeline changes or posts from layer 2 are reused, they have sentiment scores but no other enriched metadata (e.g., pain_categories, is_maintainer)
- **Non-obvious:** Callers might assume returned posts are the only ones mutated
- Test coverage doesn't explicitly validate this behavior

**Impact:** Low in current linear pipeline (failed posts discarded), but fragile if filter layers are reordered or posts cached.

**Recommendation:** Add docstring note documenting side effect:
```python
def apply(self, posts: List[RawPost]) -> List[RawPost]:
    """Return posts with combined sentiment < −0.05; store score on post.
    
    Side effect: sentiment is computed and stored on ALL input posts,
    not just those passing the threshold.
    """
```

---

### 3. **Log-Normalization Edge Case with Negative Inputs [MEDIUM]**

**Location:** `radar/ranking/scorer.py:84-92`

**Code:**
```python
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
```

**Problems:**
- **No input validation:** Doesn't check that `value >= 0`. If karma or engagement is negative, `log10(value + 1)` with value < -0.5 produces negative output
- **Redundant check:** `if denom == 0` is unreachable: if `max_value > -1`, then `log10(max_value + 1) != 0`
- **Fragile recovery:** Final clamp catches negative results, but semantically it's brittle — should validate inputs explicitly

**Example:**
```python
_log10_norm(-0.6, 100)  # log10(-0.6 + 1) = log10(0.4) ≈ -0.398 → clamped to 0.0
```

**Recommendation:**
```python
@staticmethod
def _log10_norm(value: float, max_value: float) -> float:
    """log10(value + 1) / log10(max_value + 1), clamped [0, 1].
    
    Assumes value, max_value >= 0.
    """
    if max_value <= 0:
        return 0.0
    value = max(0.0, value)  # Explicit non-negative enforcement
    denom = math.log10(max_value + 1)
    result = math.log10(value + 1) / denom
    return max(0.0, min(1.0, result))
```

---

## Minor Issues

### 4. **Dead Code: Unused `_log1p_norm()` Method [LOW]**

**Location:** `radar/ranking/scorer.py:95-103`

**Code:**
```python
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
```

**Problem:**  
Method is never called anywhere in the codebase. `score_batch()` uses `_log10_norm()` exclusively.

**Recommendation:** Remove or document if reserved for future alternative normalization strategy.

---

### 5. **Inefficient Maintainer Boost Signal Recount [LOW]**

**Location:** `radar/ranking/scorer.py:122-132`

**Code:**
```python
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
```

**Problem:**
- **Recomputation:** For every post that passed the maintainer filter, this re-instantiates `MaintainerContextFilter` and re-scans text
- **Missing cache:** Filter layer already counted signals to determine `is_maintainer_context=True`, but didn't store the count
- **Circular import:** Imports `MaintainerContextFilter` at runtime within a static method

**Impact:** Negligible in current batch sizes (10–100 posts), but poor design if scaling.

**Recommendation:** Add `maintainer_signal_count: int = 0` field to `RawPost` model, populate in `MaintainerContextFilter.apply()`, and use cached value in scorer.

---

### 6. **Float Precision at Sentiment Threshold [LOW]**

**Location:** `radar/ranking/filters.py:104`

**Code:**
```python
PASS_THRESHOLD = -0.05
```

**Problem:**  
Floating-point rounding can cause boundary issues. Posts at exactly -0.04999999... may filter inconsistently depending on representation.

**Recommendation:** Document expected behavior or use a small epsilon buffer if needed.

---

### 7. **No Text Length Bounds Checking [LOW]**

**Location:** `radar/ranking/filters.py:129-147`

**Code:**
```python
def _combined_score(self, text: str) -> float:
    """Return combined VADER+TextBlob sentiment score.
    Range is approximately [-1, +1].  Negative values indicate pain.
    """
    vader_score = 0.0
    textblob_score = 0.0
    
    if _VADER_AVAILABLE and self._vader is not None:
        vs = self._vader.polarity_scores(text)
        vader_score = vs["compound"]
    if _TEXTBLOB_AVAILABLE:
        try:
            tb = TextBlob(text)
            textblob_score = tb.sentiment.polarity
        except Exception:
            textblob_score = 0.0
    
    return self.vader_weight * vader_score + self.textblob_weight * textblob_score
```

**Problem:**  
No bounds on text length. VADER and TextBlob can handle arbitrary sizes, but no documented behavior for extremely large posts (MB+).

**Impact:** Low — unlikely in practice with HN/Reddit/social media posts.

---

## Test Coverage Analysis

✅ **21 tests passing**  
✅ Core sentiment logic tested (positive/negative/neutral)  
✅ Filter pipeline end-to-end  
✅ Keyword matching and categorization  
✅ Maintainer context signals  

**Gaps:**
- No explicit tests for sentiment normalization edge cases (extreme values ±0.99)
- No tests for numerical precision/rounding
- No tests for large text inputs (1MB+)
- No tests validating mutation side-effects on filtered-out posts

---

## Scoring Accuracy Assessment

### Normalization Logic ✓
- **Influence (karma):** Log-normalized, appropriate for power-law distributions
- **Engagement (score + comments):** Log-normalized, matches PRD spec
- **Pain factor:** Stepped multiplier (1.0, 1.2, 1.5) — reasonable, clearly defined
- **Sentiment factor:** **1.0 + abs(sentiment)** — works but needs clamping (see Issue #1)
- **Maintainer boost:** 1.0 / 1.25 — conservative, avoids over-weighting

### Ranking Order
Posts are correctly sorted descending by `final_score = base_score * pain_factor * sentiment_factor * maintainer_boost`. Formula matches PRD FR-3.x specification.

### Edge Cases
| Scenario | Behavior | Risk |
|----------|----------|------|
| Zero karma/engagement | Normalized to 0.0 → base_score = 0 | ✓ Safe |
| Extreme sentiment (-0.99) | Factor = 1.99 → ~2x amplification | ⚠ Unclamped |
| No pain categories | pain_factor = 1.0 → no boost | ✓ Safe |
| No maintainer signals | boost = 1.0 → no boost | ✓ Safe |
| Both sentiment values None | Falls back to 0.0 → factor = 1.0 | ⚠ No validation |

---

## Summary

**Strengths:**
- Clean separation of concerns (filter layers, scorer)
- Log-normalization appropriate for ranking signal
- Comprehensive test coverage for main paths
- Handles missing external libraries gracefully (VADER/TextBlob)

**Weaknesses:**
- Sentiment factor lacks defensive bounds checking
- Mutation side-effects not documented
- Dead code (`_log1p_norm()`)
- Inefficient signal recomputation

**Overall Conclusion:**  
System is **functionally correct** and produces reasonable ranking order. However, **normalization robustness** should be improved to handle edge cases in sentiment amplification and input validation. Recommend addressing HIGH/MEDIUM issues before scaling to larger post batches.

---

## Recommendations (Priority)

| Priority | Issue | Effort | Impact |
|----------|-------|--------|--------|
| HIGH | Fix sentiment amplification clamping | 5 min | Prevent unbounded scores |
| MEDIUM | Document sentiment mutation side-effect | 2 min | Reduce future fragility |
| MEDIUM | Add input validation to `_log10_norm()` | 5 min | Explicit safety |
| LOW | Remove `_log1p_norm()` dead code | 1 min | Code hygiene |
| LOW | Cache maintainer signal count | 15 min | Optional optimization |
| LOW | Add robustness tests | 20 min | Coverage improvement |

