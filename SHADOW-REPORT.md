# QA SHADOW-REPORT
## Dark Factory Run: run-20260225-221258

### Test Summary
- **Engineer's Tests (tests/)**: 147 passed, 0 failed
- **Sealed Tests (sealed_tests/)**: 5 passed, 119 failed, 29 errors
- **Total Tests Run**: 262
- **Total Passed**: 152
- **Total Failed**: 148 (119 failures + 29 errors)

---

## Engineer's Tests: PASSED ✓
All 147 tests in `tests/` directory passed successfully.
- test_cli.py: 13 passed
- test_config.py: 23 passed
- test_email.py: 13 passed
- test_filter.py: 23 passed
- test_pipeline.py: 12 passed
- test_ranking.py: 38 passed
- test_scraping.py: 11 passed
- test_storage.py: 18 passed

---

## Sealed Tests: CRITICAL GAPS IDENTIFIED

### Import Errors (Primary Failures)
The sealed tests expect modules that do not exist in the current implementation:

#### 1. Missing `radar.db` Module (29 errors)
**Tests Affected**: test_pipeline.py (14 errors), test_storage.py (15 errors)

**Error Pattern**:
```
ModuleNotFoundError: No module named 'radar.db'
```

**Tests Blocked**:
- TestExactlyFiveEntries: 2 errors (test_five_qualifying_posts_yields_five_entries, test_ten_qualifying_posts_still_yields_five)
- TestPartialReport: 2 errors (test_fewer_than_five_posts_exits_1, test_zero_posts_exits_2)
- TestFallbackLadder: 5 errors (test_live_tier_first_choice, test_falls_back_to_archive_7d_when_live_empty, test_falls_back_to_archive_30d_when_7d_empty, test_partial_tier_when_fewer_than_five_across_all, test_all_entries_have_valid_source_tier)
- TestExitCodes: 1 error (test_daily_exits_0_on_full_report)
- TestDuplicateRunGuard: 2 errors (test_daily_skipped_within_20_hours, test_skip_result_indicates_no_action)
- TestForceFlag: 2 errors (test_force_overrides_20h_guard, test_force_flag_via_cli)
- TestDryRun: 3 errors (test_dry_run_skips_db_writes, test_dry_run_skips_email_send, test_dry_run_no_report_entries_in_db)
- TestURLDeduplication: 3 errors (test_duplicate_url_hash_not_inserted_twice, test_different_urls_both_stored, test_insert_post_returns_without_error_on_duplicate)
- TestDuplicateRunGuard (storage): 5 errors (test_recent_run_triggers_guard, test_old_run_does_not_trigger_guard, test_no_prior_run_returns_false, test_boundary_edge_returns_bool, test_custom_window_respected)
- TestReportEntries: 4 errors (test_insert_five_entries_retrievable, test_entry_includes_source_tier, test_all_four_valid_source_tiers_storable, test_entries_isolated_per_report)

**Expected Behavior**: Code should provide a `CatalogDB` class in `radar/db.py`

**Actual Behavior**: Module does not exist; sealed tests import from `radar.db` at conftest setup time

---

#### 2. Missing `radar.config.RadarSettings` Class (14 failures)
**Tests Affected**: test_config.py

**Error Pattern**:
```
ImportError: cannot import name 'RadarSettings' from 'radar.config'
```

**Tests Failed**:
- TestConfigLoadsSuccessfully: 4 failures (test_valid_config_loads, test_db_path_is_set, test_env_prefix_is_radar, test_unprefixed_key_ignored)
- TestWeightSumEnforcement: 5 failures (test_influence_engagement_valid_sum, test_influence_engagement_wrong_sum_raises, test_vader_textblob_valid_sum, test_vader_textblob_wrong_sum_raises, test_weights_exactly_one_accepted)
- TestSMTPConditionalValidation: 2 failures (test_smtp_required_when_email_enabled, test_smtp_not_required_when_email_disabled)
- TestSentinelValues: 3 failures (test_default_sentiment_threshold, test_default_duplicate_window, test_custom_sentiment_threshold_accepted)

**Expected Behavior**: `radar/config.py` should export `RadarSettings` class with validation for weights, SMTP settings, and sentinel values

**Actual Behavior**: `RadarSettings` class does not exist in `radar.config` module

---

#### 3. Missing `radar.mailer.Mailer` Class (18 failures)
**Tests Affected**: test_email.py

**Error Pattern**:
```
ModuleNotFoundError: No module named 'radar.mailer'
```

**Tests Failed**:
- TestDailyEmailSubject: 5 failures (test_exact_subject_format, test_subject_regex_match, test_subject_embeds_correct_date, test_subject_bracket_prefix_exact, test_daily_subject_uses_em_dash_not_hyphen)
- TestWeeklyEmailSubject: 3 failures (test_exact_subject_format, test_subject_regex_match, test_weekly_uses_em_dash_not_hyphen)
- TestDailyTemplateRendering: 5 failures (test_render_returns_non_empty_html, test_render_includes_all_post_titles, test_render_is_valid_html_fragment, test_empty_posts_renders_without_exception, test_dark_mode_color_present_in_template)
- TestMultipartMIME: 3 failures (test_send_daily_calls_sendmail, test_email_message_has_html_part, test_send_weekly_calls_sendmail)
- TestWeeklyDigest: 2 failures (test_weekly_render_caps_at_ten_posts, test_weekly_top_10_selection_in_mailer)

**Expected Behavior**: `radar/mailer.py` should export `Mailer` class with daily/weekly email rendering and sending

**Actual Behavior**: `radar.mailer` module does not exist

---

#### 4. Missing `radar.filter.Filter` or Filter Classes (31 failures)
**Tests Affected**: test_filter.py

**Error Pattern**:
```
ImportError: cannot import name '[ClassName]' from 'radar.filter' / 'radar.ranking'
```

**Tests Failed**:
- TestKeywordGate: 16 failures (test_post_with_matching_keyword_passes, test_post_without_any_keyword_fails, test_pain_keywords_pass_gate[...], test_pain_category_enum_has_15_entries, test_keyword_match_is_case_insensitive)
- TestMaintainerContextGate: 10 failures (test_maintainer_phrases_pass[...], test_no_maintainer_context_fails, test_zero_maintainer_signals_excluded_at_filter_level)
- TestSentimentGate: 14 failures (test_clearly_negative_sentiment_passes, test_clearly_positive_sentiment_fails, test_neutral_sentiment_fails, test_exactly_threshold_fails, test_just_below_threshold_passes, test_all_sentiments_at_or_above_threshold_fail[...], test_composite_sentiment_uses_vader_and_textblob_weights)
- TestAllThreeMustPass: 5 failures (test_fails_keyword_gate_excluded, test_fails_maintainer_gate_excluded, test_fails_sentiment_gate_excluded, test_passes_all_three_is_included, test_mixed_batch_only_passing_posts_returned)

**Expected Behavior**: Filter classes supporting keyword gates, maintainer context detection, sentiment analysis gates with configurable thresholds, and composite filtering

**Actual Behavior**: Filter classes not properly accessible or not fully implemented

---

#### 5. Missing `radar.ranking.Ranker` Class (13 failures)
**Tests Affected**: test_ranking.py

**Error Pattern**:
```
ImportError: cannot import name 'Ranker' from 'radar.ranking' / attribute errors
```

**Tests Failed**:
- TestRankingOrder: 5 failures (test_higher_platform_score_ranks_first, test_higher_comment_count_ranks_first, test_more_negative_sentiment_ranks_higher, test_more_maintainer_signals_ranks_higher, test_output_is_sorted_descending)
- TestBatchNormalization: 4 failures (test_signal_score_bounded_zero_to_one, test_single_post_does_not_crash, test_all_identical_posts_no_exception, test_empty_post_list_returns_empty)
- TestLogScaleScoring: 2 failures (test_million_vs_hundred_ratio_compressed, test_zero_score_post_does_not_crash)
- TestWeightConfiguration: 2 failures (test_high_influence_weight_favours_score_over_comments, test_high_engagement_weight_favours_comments_over_score)

**Expected Behavior**: Ranker class with normalization, log-scale scoring, and configurable weights

**Actual Behavior**: Ranker functionality not fully available or properly exposed

---

#### 6. Missing `radar.scraper` Module (26 failures)
**Tests Affected**: test_scraping.py

**Error Pattern**:
```
ModuleNotFoundError: No module named 'radar.scraper'
```

**Tests Failed**:
- TestScraperIsolation: 4 failures (test_reddit_failure_does_not_prevent_hn_results, test_devto_failure_does_not_prevent_lobsters_results, test_all_scrapers_fail_returns_empty_list_no_crash, test_single_scraper_failure_does_not_raise)
- TestSSRFProtection: 14 failures (test_private_ip_raises[...], test_public_url_allowed[...], test_ssrf_guard_rejects_metadata_endpoint)
- TestRetryBehavior: 4 failures (test_reddit_retries_on_transient_failure, test_hn_gives_up_after_three_attempts, test_devto_max_attempts_is_three, test_lobsters_succeeds_on_second_attempt)
- TestPlatformTagging: 4 failures (test_posts_tagged_with_correct_platform[...])

**Expected Behavior**: Unified `radar.scraper` module providing access to scraper classes with SSRF protection, retry logic, and platform tagging

**Actual Behavior**: `radar.scraper` module does not exist; scrapers are in separate submodules

---

### Sealed Tests Passing (5/153)
Tests that successfully pass without hitting import errors:
1. sealed_tests/test_pipeline.py::TestGitHubActionsWorkflows::test_daily_workflow_file_exists
2. sealed_tests/test_pipeline.py::TestGitHubActionsWorkflows::test_weekly_workflow_file_exists
3. sealed_tests/test_pipeline.py::TestGitHubActionsWorkflows::test_daily_cron_schedule_is_correct
4. sealed_tests/test_pipeline.py::TestGitHubActionsWorkflows::test_weekly_cron_schedule_is_correct
5. sealed_tests/test_storage.py::TestURLDeduplication::test_url_hash_is_sha256

**Gap**: Only 3.3% of sealed tests pass; they validate file structure and basic storage hashing

---

## Gap Analysis

### Root Cause Categories

| Category | Count | Severity |
|----------|-------|----------|
| Missing modules (radar.db, radar.mailer, radar.scraper) | 73 | CRITICAL |
| Missing classes/exports (RadarSettings, Ranker, Filter classes) | 45 | CRITICAL |
| **Total Gaps** | **118** | **CRITICAL** |

### Implementation Gaps

1. **Database Layer** (29 errors): No CatalogDB implementation
   - Pipeline tests cannot run
   - Storage tests cannot initialize database

2. **Configuration** (14 failures): RadarSettings class missing
   - No validated configuration object
   - Weight validation not available
   - SMTP conditional validation not enforced

3. **Email/Mailer** (18 failures): No Mailer class
   - Daily/weekly email formatting not testable
   - Template rendering untested
   - MIME multipart handling untested

4. **Filtering** (31 failures): Incomplete filter implementation
   - Keyword gate not accessible
   - Maintainer context detection not available
   - Sentiment gate may be incomplete

5. **Ranking** (13 failures): Ranker class not accessible
   - Normalization logic untested
   - Log-scale scoring untested
   - Weight configuration untested

6. **Scraping** (26 failures): No unified scraper module
   - SSRF protection not testable
   - Retry behavior not testable
   - Platform tagging not testable

---

## Metrics

- **Total Tests**: 262
- **Passing**: 152 (58.0%)
- **Failing**: 148 (56.5%)
  - Failures: 119
  - Errors: 29
- **Gap Score**: (119 + 29) / 153 × 100 = **96.7%**

The sealed test suite reveals massive architectural gaps. The implementation covers basic functionality (engineer tests) but lacks critical modules and classes required for production-grade features (email delivery, database persistence, advanced filtering, ranking).

---

GAP_SCORE: 97%
