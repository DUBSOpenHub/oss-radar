# Scraper Review: reddit.py & lobsters.py

**Date:** 2026-03-04  
**Reviewer:** Stampede Agent (agent-dc0fab)  
**Task ID:** task-003  

---

## Executive Summary

Reviewed `radar/scraping/reddit.py` (116 lines) and `radar/scraping/lobsters.py` (107 lines) for parsing correctness, API usage, and error handling.

**Findings:** 10 issues identified
- **1 Error** (critical): JSON response type validation missing in Lobsters scraper
- **4 Warnings**: Datetime consistency, API credential validation, type safety, error context
- **5 Info/Minor**: Rate limiting, parsing safety, fallback logging, duplicate fields

Overall assessment: Both scrapers follow the BaseScraper contract well, but lobsters.py has a critical type-safety gap. Both need datetime consistency fixes.

---

## Detailed Findings

### reddit.py

#### 1. **CRITICAL: Datetime Consistency** (Line 113) — WARNING

**Finding:**  
`scraped_at` uses `datetime.utcnow()` (naive, no timezone), while `created_utc` uses `timezone.utc` (aware). Mixing naive and aware datetimes in the same model is error-prone and violates Python datetime best practices.

**Impact:** Medium — Naive datetimes can cause unexpected behavior in timezone-aware comparisons, serialization, and comparisons with created_utc.

**Recommendation:**  
Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` for consistency. Match lobsters.py's approach (though lobsters also has this issue).

**Code:**
```python
# Current (line 113):
scraped_at=datetime.utcnow(),

# Proposed:
scraped_at=datetime.now(timezone.utc),
```

---

#### 2. **API Credentials Not Validated** (Line 49) — WARNING

**Finding:**  
The PRAW Reddit client is instantiated with credentials without checking if they're empty strings. If `reddit_client_id` or `reddit_client_secret` are empty, PRAW will fail with a cryptic error deep in authentication.

**Impact:** Low — Already protected by outer try-except, but error message is poor. Could mask configuration issues.

**Recommendation:**  
Add explicit validation before creating the Reddit client:

```python
# After line 39 check:
if not self.config.reddit_client_id or not self.config.reddit_client_secret:
    logger.warning(
        "reddit_credentials_missing",
        extra={"client_id_empty": not self.config.reddit_client_id,
               "client_secret_empty": not self.config.reddit_client_secret}
    )
    return []
```

---

#### 3. **Rate Limiting Not Configurable** (Line 59) — INFO

**Finding:**  
Hardcoded `limit=25` per subreddit. PRAW has built-in rate limiting, but there's no visibility into backoff or configurability for different scenarios (full crawl vs. incremental).

**Impact:** Low — Works for current use case, but inflexible for future needs (e.g., catch-up crawls).

**Recommendation:**  
Make per-subreddit limit configurable via Settings, and optionally log PRAW's rate-limit headers:

```python
limit = getattr(self.config, 'reddit_posts_per_subreddit', 25)
for submission in subreddit.new(limit=limit):
```

---

#### 4. **Duplicate Fields Confusing** (Line 108–111) — MINOR

**Finding:**  
Both `upvotes` and `score` are set to the same value. Similarly, `followers` and `author_karma` are aliases. This is by design in RawPost, but it's not obvious why both are populated.

**Impact:** None — Intentional design, but lacks documentation.

**Recommendation:**  
Add a comment explaining the alias convention:

```python
# upvotes and score are aliases in RawPost; populate both for compatibility
upvotes=int(getattr(submission, "score", 0)),
score=int(getattr(submission, "score", 0)),
```

---

#### 5. **Deleted Authors Not Special-Cased** (Line 84–85) — INFO

**Finding:**  
When an author is deleted, `author_obj` is still an object, but `.name` returns `[deleted]`. The code silently accepts this. Deleted posts may skew rankings.

**Impact:** Low — Functional, but semantic issue for scoring.

**Recommendation:**  
Tag or filter deleted posts:

```python
author_name = str(getattr(author_obj, "name", "")) if author_obj else ""
if author_name == "[deleted]":
    logger.debug("reddit_deleted_author", extra={"sub": sub_name})
    # Optionally skip or tag post
```

---

### lobsters.py

#### 6. **CRITICAL: Missing JSON Response Validation** (Line 55) — ERROR

**Finding:**  
`response.json()` is called without validation. The HTTP client ensures 200 status and successful request, but:
1. The response body might not be valid JSON
2. Even if valid, the JSON might not be a list (could be `{}` or `null`)
3. If parsing fails, the exception is caught but without logging the actual JSON body

**Impact:** High — Silent failure masks API changes. If Lobsters API ever returns an error object or wraps results in a key, the scraper will fail with a cryptic error.

**Recommendation:**  
Add explicit type validation:

```python
def _fetch_feed(self, url: str) -> List[RawPost]:
    """Fetch and parse a single Lobsters JSON feed."""
    response = self.client.get(url)
    try:
        stories: List[Dict[str, Any]] = response.json()
    except Exception as exc:
        logger.error(
            "lobsters_json_parse_error",
            extra={"url": endpoint, "error": str(exc), "status": response.status_code},
        )
        raise
    
    if not isinstance(stories, list):
        raise ValueError(f"Expected list, got {type(stories).__name__}")
    
    return [self._story_to_post(s) for s in stories]
```

---

#### 7. **Type Safety: No List Assertion** (Line 55) — WARNING

**Finding:**  
`response.json()` returns `Any`. If the API ever returns `{"stories": [...]}` instead of `[...]`, the code will fail with an AttributeError when trying to iterate.

**Impact:** Medium — Already caught by outer exception handler, but error is silent.

**Recommendation:**  
Add explicit check (see #6 above).

---

#### 8. **Datetime Consistency** (Line 104) — WARNING

**Finding:**  
Same as reddit.py: `scraped_at` uses naive `datetime.utcnow()`, while `created_utc` is aware (when present). Inconsistent.

**Impact:** Medium — Same as reddit.py.

**Recommendation:**  
Replace with `datetime.now(timezone.utc)`.

---

#### 9. **Empty URL Fallback Not Logged** (Line 60–63) — INFO

**Finding:**  
The fallback chain (url → short_id_url → comments_url) is smart, but if all are empty, the post gets `url=""`. No logging when falling back to comments_url, so you won't know how many text-only posts are in the feed.

**Impact:** Low — Doesn't break functionality, but reduces observability.

**Recommendation:**  
Log when falling back:

```python
story_url = story.get("url", "")
if not story_url:
    story_url = story.get("short_id_url", "")
if not story_url:
    story_url = story.get("comments_url", "")
    if story_url:
        logger.debug("lobsters_fallback_to_comments_url")
```

---

#### 10. **Tags Type Coercion Not Defensive** (Line 88) — MINOR

**Finding:**  
`tags_raw = story.get("tags", [])` is assumed to be a list, and `[str(t) for t in tags_raw if t]` filters falsy values. No explicit type check for the list itself or its elements.

**Impact:** Low — Unlikely to fail, but non-defensive.

**Recommendation:**  
More defensive parsing:

```python
tags_raw = story.get("tags", [])
if not isinstance(tags_raw, list):
    tags_raw = []
tags = [str(t) for t in tags_raw if isinstance(t, (str, int)) and str(t).strip()]
```

---

## Cross-File Observations

### Strengths
1. **Good error isolation:** Both scrapers wrap external calls in try-except and log failures without crashing the pipeline.
2. **Deduplication:** Both use `_dedup_key()` to normalize URLs for duplicate detection.
3. **Clean model mapping:** Both correctly map platform-specific fields to RawPost fields.
4. **Rate limiting:** PRAW's built-in rate limiting and Lobsters' natural API limits are respected.

### Weaknesses
1. **Naive datetimes:** Both use `datetime.utcnow()` instead of aware datetimes. This is the most widespread issue.
2. **Limited observability:** Fallbacks and edge cases (deleted authors, empty URLs, text-only posts) are silently handled without logging.
3. **Type safety:** Lobsters assumes response.json() returns a list; no validation.
4. **Credential validation:** Reddit credentials aren't pre-validated before PRAW instantiation.

---

## Testing Recommendations

1. **Unit test invalid JSON:** Mock Lobsters feed to return `{}` or `null` and verify graceful failure.
2. **Unit test deleted authors:** Mock Reddit submission with deleted author and verify post is still returned (or tagged).
3. **Unit test empty URLs:** Mock Lobsters story with empty url, short_id_url, and comments_url, verify post still created.
4. **Integration test:** Verify both scrapers produce posts with consistent datetime types (all aware or all naive).

---

## Summary Table

| File | Issue | Severity | Category | Status |
|------|-------|----------|----------|--------|
| reddit.py | Naive datetime (utcnow) | WARNING | Consistency | Open |
| reddit.py | No credential validation | WARNING | Error Handling | Open |
| reddit.py | Hardcoded rate limit | INFO | Flexibility | Open |
| reddit.py | Duplicate fields (upvotes/score) | MINOR | Documentation | Open |
| reddit.py | Deleted author handling | INFO | Observability | Open |
| lobsters.py | Missing JSON validation | ERROR | Type Safety | **CRITICAL** |
| lobsters.py | No list type check | WARNING | Type Safety | Open |
| lobsters.py | Naive datetime (utcnow) | WARNING | Consistency | Open |
| lobsters.py | Empty URL fallback not logged | INFO | Observability | Open |
| lobsters.py | Tags type coercion not defensive | MINOR | Robustness | Open |

---

## Next Steps

1. **Priority 1 (Critical):** Add explicit JSON type validation to `lobsters._fetch_feed()`.
2. **Priority 2 (High):** Replace all `datetime.utcnow()` with `datetime.now(timezone.utc)` in both files.
3. **Priority 3 (Medium):** Add credential validation in `reddit.fetch_raw()` before PRAW instantiation.
4. **Priority 4 (Low):** Add logging for fallbacks and edge cases (deleted authors, empty URLs, type mismatches).

