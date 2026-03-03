# Test and CI Audit Findings

**Audit Date:** 2024-01-15  
**Scope:** tests/ directory and .github/workflows/ configurations  
**Total Test Cases:** 217 collected  
**Agent:** agent-808904  
**Task:** task-008

---

## Executive Summary

OSS Radar has a comprehensive test suite with 217 test cases covering all major modules. However, this audit identified 23 findings across test coverage gaps, flaky test patterns, missing assertions, CI configuration issues, and workflow security concerns. Priority focus areas: async test coverage, network-dependent tests, and workflow secret management.

---

## 1. Test Coverage Gaps

### 1.1 Missing Async Tests for LLMBackend
**File:** tests/test_llm.py  
**Line:** 47-51  
**Severity:** MEDIUM  
**Description:** Only one async test (`test_dry_run_async`) exists for `LLMBackend.complete()`. The async path for GitHub Models API and amplifier fallback is not tested.  
**Fix:** Add async variants of `test_github_models_success` and `test_github_models_failure_falls_to_amplifier`.

```python
async def test_github_models_async_success(self, mock_exec):
    # Test async complete() with GitHub Models success
    pass

async def test_amplifier_fallback_async(self, mock_exec):
    # Test async complete() with fallback to amplifier
    pass
```

---

### 1.2 No Tests for Database Connection Failures
**File:** tests/test_storage.py  
**Line:** N/A  
**Severity:** MEDIUM  
**Description:** No tests validate behavior when SQLite connection fails (e.g., permission denied, disk full, corrupted DB).  
**Fix:** Add test cases for connection failures and recovery.

```python
def test_connection_failure_raises():
    with pytest.raises(sqlite3.OperationalError):
        Database("/root/forbidden.db")

def test_corrupted_db_recovery(tmp_path):
    db_path = tmp_path / "corrupt.db"
    db_path.write_text("not a database")
    # Should raise or attempt recovery
```

---

### 1.3 Missing Edge Cases for Backfill Manager
**File:** tests/test_pipeline.py  
**Line:** 89-115  
**Severity:** LOW  
**Description:** No tests for: (a) all 5 posts from archive when 0 live, (b) mixed live + 7d + 30d fallback chain, (c) reported posts excluded from backfill.  
**Fix:** Add comprehensive backfill scenario tests.

```python
def test_zero_live_five_from_archive(self, tmp_db):
    # Insert 5 archive posts, pass [] as live
    # Verify result has 5 from archive

def test_mixed_tier_backfill(self, tmp_db):
    # 2 live + 2 from 7d + 1 from 30d = 5 total
```

---

### 1.4 No Integration Test for Reddit Scraper
**File:** tests/test_scraping.py  
**Line:** N/A  
**Severity:** MEDIUM  
**Description:** No tests for Reddit scraper exist. The module is conditional (reddit_enabled flag) but untested.  
**Fix:** Add mocked tests for Reddit scraper similar to HN/DevTo/Lobsters patterns.

```python
class TestRedditScraper:
    def test_fetch_returns_raw_posts(self, settings, mock_client):
        # Mock PRAW responses
        pass

    def test_scrape_isolates_errors(self, settings, mock_client):
        pass
```

---

### 1.5 No Tests for Weekly Report Breakdown Edge Cases
**File:** tests/test_email.py  
**Line:** 195-204  
**Severity:** LOW  
**Description:** Weekly report platform/category breakdowns tested only with populated data. No tests for: (a) empty breakdowns, (b) single-platform weeks, (c) category with 0 posts.  
**Fix:** Add edge case tests for breakdown rendering.

---

### 1.6 LLM Summarizer Concurrency Not Tested
**File:** tests/test_llm.py  
**Line:** 132-189  
**Severity:** LOW  
**Description:** `summarize_posts()` processes posts serially. No tests verify behavior under concurrent LLM calls or rate-limiting scenarios.  
**Fix:** Add concurrency/rate-limit simulation tests.

---

## 2. Flaky Test Patterns

### 2.1 Time-Based Flakiness in Duplicate Run Guard
**File:** tests/test_pipeline.py  
**Line:** 166-182  
**Severity:** MEDIUM  
**Description:** `test_duplicate_run_guard_without_force` uses frozen time from `conftest.py` (2024-01-15). If the frozen time is within `duplicate_run_hours` of a recent report, test could flake.  
**Fix:** Explicitly set report timestamp in test to be outside the guard window.

```python
def test_duplicate_run_guard_without_force(self, tmp_db, mock_settings):
    # Set report timestamp to 2024-01-14 (25 hours ago)
    # Ensure guard triggers correctly
```

---

### 2.2 Sentiment Filter Tests Depend on External Libraries
**File:** tests/test_filter.py  
**Line:** 157-182  
**Severity:** MEDIUM  
**Description:** `SentimentFilter` uses VADER (bundled) and TextBlob (optional). Tests like `test_combined_score_computed` relax assertions (`assert score != 0.0 or True`) because TextBlob may not be installed. This makes tests non-deterministic.  
**Fix:** Mock sentiment backends or skip tests when dependencies missing.

```python
@pytest.mark.skipif(not HAS_TEXTBLOB, reason="TextBlob not installed")
def test_combined_score_computed(self):
    # Assert exact score behavior
```

---

### 2.3 Network-Dependent Validation Command
**File:** tests/test_cli.py  
**Line:** 207-217  
**Severity:** HIGH  
**Description:** `test_validate_fails_gracefully_no_internet` assumes network checks may fail in test env. This test will flake if run in CI with internet access vs. airgapped environments.  
**Fix:** Mock network requests in validate command tests.

```python
@patch("requests.get")
def test_validate_fails_gracefully_no_internet(mock_get, tmp_path):
    mock_get.side_effect = ConnectionError("No network")
    result = runner.invoke(app, ["validate", "--db-path", str(tmp_path / "test.db")])
    assert result.exit_code == 1
```

---

### 2.4 Deterministic Seed Not Applied to All Tests
**File:** tests/conftest.py  
**Line:** 22-26  
**Severity:** LOW  
**Description:** `_deterministic_seed` fixture resets `random.seed(42)` but does not control `uuid`, `os.urandom`, or other entropy sources. Tests generating random data may still flake.  
**Fix:** Seed all entropy sources or use `freezegun` for full determinism.

---

## 3. Missing Assertions

### 3.1 Mock Call Verification Missing in CLI Tests
**File:** tests/test_cli.py  
**Line:** 119-127, 148-176  
**Severity:** LOW  
**Description:** `test_daily_exits_zero_on_full_report` verifies exit code but does not assert that `PipelineOrchestrator.run_daily` was called with correct arguments.  
**Fix:** Add mock call assertions.

```python
def test_daily_exits_zero_on_full_report(self, tmp_path):
    with patch("radar.pipeline.PipelineOrchestrator.run_daily") as mock_run:
        mock_run.return_value = full_daily_report()
        result = runner.invoke(app, ["daily", "--db-path", str(tmp_path / "test.db"), "--no-email"])
    assert result.exit_code == 0
    mock_run.assert_called_once()  # ADD THIS
```

---

### 3.2 No Validation of Email MIME Boundaries
**File:** tests/test_email.py  
**Line:** 224-240  
**Severity:** LOW  
**Description:** `test_build_mime_has_both_parts` checks content types but does not validate MIME boundary correctness or part ordering.  
**Fix:** Add assertions for MIME structure integrity.

---

### 3.3 FilterPipeline Tests Missing Layer-by-Layer Assertions
**File:** tests/test_filter.py  
**Line:** 189-233  
**Severity:** MEDIUM  
**Description:** `test_full_pain_post_passes` and `test_unrelated_post_rejected` do not verify which filter layer caused rejection. Debugging failures is difficult.  
**Fix:** Add intermediate assertions for each filter layer.

```python
def test_full_pain_post_passes(self):
    fp = FilterPipeline()
    post = make_post(...)
    # Layer 1: Keyword
    after_kw = fp.filters[0].apply([post])
    assert len(after_kw) == 1, "Failed keyword filter"
    # Layer 2: Maintainer
    after_mc = fp.filters[1].apply(after_kw)
    assert len(after_mc) == 1, "Failed maintainer filter"
    # Layer 3: Sentiment
    result = fp.filters[2].apply(after_mc)
    assert len(result) == 1, "Failed sentiment filter"
```

---

### 3.4 No Assertion on LLM Token Counts in Summarizer Tests
**File:** tests/test_llm.py  
**Line:** 162-171  
**Severity:** LOW  
**Description:** `test_successful_summary` does not verify that token usage is tracked correctly.  
**Fix:** Assert token counts in mock response.

---

## 4. CI Configuration Issues

### 4.1 Pinned Action Versions Without Dependabot
**File:** .github/workflows/daily.yml, weekly.yml, codeql.yml  
**Line:** Multiple  
**Severity:** MEDIUM  
**Description:** Actions are pinned to commit SHAs (e.g., `actions/checkout@34e114876b0b...`) but no Dependabot config exists to keep them updated. Outdated actions may have security vulnerabilities.  
**Fix:** Add `.github/dependabot.yml` to auto-update actions.

```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
```

---

### 4.2 No Timeout on Individual Steps
**File:** .github/workflows/daily.yml  
**Line:** N/A  
**Severity:** LOW  
**Description:** Job-level timeout is 30 minutes but no per-step timeouts. A hanging step (e.g., `pip install`) could consume the full timeout.  
**Fix:** Add `timeout-minutes` to critical steps.

```yaml
- name: Install dependencies
  timeout-minutes: 5
  run: pip install -e .
```

---

### 4.3 Artifact Download Failures Silently Ignored
**File:** .github/workflows/daily.yml, weekly.yml  
**Line:** 51-56  
**Severity:** MEDIUM  
**Description:** `continue-on-error: true` on artifact download means failures are silent. If the artifact is missing, the pipeline starts with an empty DB, losing historical data.  
**Fix:** Log warning on failure and create empty DB explicitly.

```yaml
- name: Download latest catalog artifact
  id: download_artifact
  uses: actions/download-artifact@...
  continue-on-error: true

- name: Check artifact status
  run: |
    if [ "${{ steps.download_artifact.outcome }}" = "failure" ]; then
      echo "WARNING: No catalog artifact found, starting fresh"
      mkdir -p ~/.radar && touch ~/.radar/catalog.db
    fi
```

---

### 4.4 Postfix Installation Not Idempotent
**File:** .github/workflows/daily.yml, weekly.yml  
**Line:** 43-49  
**Severity:** LOW  
**Description:** Postfix installation always runs even if already installed. Wastes ~10 seconds on every run.  
**Fix:** Check if postfix is already running before installing.

```bash
if ! systemctl is-active --quiet postfix; then
  sudo debconf-set-selections ...
fi
```

---

### 4.5 No Matrix Strategy for Python Versions
**File:** .github/workflows/daily.yml, weekly.yml  
**Line:** 34-38  
**Severity:** LOW  
**Description:** Workflows only test Python 3.11. No validation that code works on 3.10 or 3.12+.  
**Fix:** Add matrix strategy for Python versions.

```yaml
strategy:
  matrix:
    python-version: ["3.10", "3.11", "3.12"]
```

---

### 4.6 RADAR_EMAIL_ENABLED Logic Uses Empty String Check
**File:** .github/workflows/daily.yml  
**Line:** 67  
**Severity:** LOW  
**Description:** `${{ secrets.RADAR_EMAIL_TO != '' && 'true' || 'false' }}` treats empty string as falsy, but what if the secret is set to a single space?  
**Fix:** Use more robust check or set default in Settings model.

---

## 5. Workflow Security Issues

### 5.1 Secrets Exposed in Environment Variables
**File:** .github/workflows/daily.yml, weekly.yml  
**Line:** 59-73  
**Severity:** HIGH  
**Description:** All secrets are exposed as environment variables. If a scraper or LLM call logs environment, secrets could leak.  
**Fix:** Use GitHub Actions secret masking and avoid passing secrets to untrusted code.

```yaml
env:
  RADAR_SMTP_PASSWORD: ${{ secrets.RADAR_SMTP_PASSWORD }}
```

**Recommended:** Pass secrets only to trusted CLI commands, not to scrapers.

---

### 5.2 No CODEOWNERS File for Workflow Changes
**File:** .github/workflows/  
**Line:** N/A  
**Severity:** MEDIUM  
**Description:** No CODEOWNERS file restricts who can modify workflows. Any contributor with write access can inject malicious steps.  
**Fix:** Add `.github/CODEOWNERS` requiring admin review for workflow changes.

```
/.github/workflows/ @greggcochran
```

---

### 5.3 GitHub Script Action Uses Unrestricted Permissions
**File:** .github/workflows/daily.yml  
**Line:** 98-120  
**Severity:** LOW  
**Description:** `actions/github-script` has `issues: write` permission but script code is not audited. Malicious code could create spam issues.  
**Fix:** Limit script to specific operations or use a dedicated action.

---

### 5.4 No Signature Verification on Artifacts
**File:** .github/workflows/daily.yml  
**Line:** 51-56  
**Severity:** LOW  
**Description:** Artifact download does not verify integrity. A corrupted or tampered artifact could break the pipeline.  
**Fix:** Add checksum verification after download.

---

## 6. Test Execution Issues

### 6.1 Missing Pytest Markers for Slow Tests
**File:** tests/test_pipeline.py, tests/test_scraping.py  
**Line:** Multiple  
**Severity:** LOW  
**Description:** Some tests (e.g., full pipeline integration) are slow but not marked. Developers cannot run fast tests only.  
**Fix:** Add `@pytest.mark.slow` to integration tests.

```python
@pytest.mark.slow
def test_end_to_end_with_storage(self, tmp_path):
    pass
```

Configure in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')"
]
```

---

### 6.2 No Test for CLI Help Output
**File:** tests/test_cli.py  
**Line:** N/A  
**Severity:** LOW  
**Description:** No test validates that `radar --help` produces correct output. Users may encounter broken help text.  
**Fix:** Add test for CLI help.

```python
def test_help_output():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "daily" in result.output
```

---

## 7. Additional Recommendations

### 7.1 Add Test for Report De-duplication
**Severity:** MEDIUM  
Test that duplicate report entries (same post in multiple reports) are handled correctly.

### 7.2 Test Error Handling in Email Sender
**Severity:** MEDIUM  
No tests for SMTP connection failures or email template rendering errors.

### 7.3 Add Tests for Database Migration
**Severity:** LOW  
If DB schema changes, no tests validate migration path from old schema to new.

---

## Summary Statistics

| Category                  | Count |
|---------------------------|-------|
| Test Coverage Gaps        | 6     |
| Flaky Test Patterns       | 4     |
| Missing Assertions        | 4     |
| CI Configuration Issues   | 6     |
| Workflow Security Issues  | 4     |
| Test Execution Issues     | 2     |
| **Total Findings**        | **26**|

**High Severity:** 2  
**Medium Severity:** 10  
**Low Severity:** 14  

---

## Prioritized Action Items

1. **HIGH:** Mock network requests in `test_validate_fails_gracefully_no_internet` (Finding 2.3)
2. **HIGH:** Review secret exposure in workflow env vars (Finding 5.1)
3. **MEDIUM:** Add async LLM backend tests (Finding 1.1)
4. **MEDIUM:** Add Dependabot config for action updates (Finding 4.1)
5. **MEDIUM:** Fix artifact download failure handling (Finding 4.3)
6. **MEDIUM:** Add Reddit scraper tests (Finding 1.4)
7. **MEDIUM:** Add database connection failure tests (Finding 1.2)
8. **MEDIUM:** Add layer-by-layer assertions in filter pipeline tests (Finding 3.3)
9. **LOW:** Add slow test markers (Finding 6.1)
10. **LOW:** Add CLI help output test (Finding 6.2)

---

**End of Audit Report**
