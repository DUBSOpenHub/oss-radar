"""Tests for the synthetic data generator."""

from __future__ import annotations

from radar.models import PainCategory, RawPost
from radar.synthetic import PLATFORMS, SyntheticDataGenerator


class TestGeneratorOutput:
    """Basic generator contract tests."""

    def test_default_count_is_50(self) -> None:
        gen = SyntheticDataGenerator()
        posts = gen.generate()
        assert len(posts) == 50

    def test_custom_count(self) -> None:
        gen = SyntheticDataGenerator(count=10)
        posts = gen.generate()
        assert len(posts) == 10

    def test_zero_count_returns_empty(self) -> None:
        gen = SyntheticDataGenerator(count=0)
        assert gen.generate() == []

    def test_returns_raw_post_instances(self) -> None:
        gen = SyntheticDataGenerator(count=5, seed=42)
        posts = gen.generate()
        for p in posts:
            assert isinstance(p, RawPost)


class TestPlatformSpread:
    """All 4 platforms should be represented."""

    def test_all_platforms_present(self) -> None:
        gen = SyntheticDataGenerator(count=20, seed=1)
        posts = gen.generate()
        platforms = {p.platform for p in posts}
        assert platforms == set(PLATFORMS)

    def test_platform_distribution_roughly_even(self) -> None:
        gen = SyntheticDataGenerator(count=100, seed=1)
        posts = gen.generate()
        counts = {}
        for p in posts:
            counts[p.platform] = counts.get(p.platform, 0) + 1
        # Each platform should have at least 20% of posts
        for plat in PLATFORMS:
            assert counts.get(plat, 0) >= 20, f"{plat} only got {counts.get(plat, 0)}"


class TestDeterministicSeeding:
    """Same seed should produce identical output."""

    def test_same_seed_same_output(self) -> None:
        gen1 = SyntheticDataGenerator(count=20, seed=42)
        gen2 = SyntheticDataGenerator(count=20, seed=42)
        posts1 = gen1.generate()
        posts2 = gen2.generate()
        for p1, p2 in zip(posts1, posts2):
            assert p1.url == p2.url
            assert p1.title == p2.title
            assert p1.body == p2.body
            assert p1.platform == p2.platform

    def test_different_seeds_different_output(self) -> None:
        gen1 = SyntheticDataGenerator(count=10, seed=1)
        gen2 = SyntheticDataGenerator(count=10, seed=999)
        posts1 = gen1.generate()
        posts2 = gen2.generate()
        # Bodies should differ (titles could overlap since template pool is small)
        bodies1 = {p.body for p in posts1}
        bodies2 = {p.body for p in posts2}
        assert bodies1 != bodies2


class TestPostFields:
    """Generated posts should have valid, populated fields."""

    def test_urls_are_unique(self) -> None:
        gen = SyntheticDataGenerator(count=50, seed=7)
        posts = gen.generate()
        urls = [p.url for p in posts]
        assert len(urls) == len(set(urls))

    def test_url_hashes_populated(self) -> None:
        gen = SyntheticDataGenerator(count=5, seed=7)
        posts = gen.generate()
        for p in posts:
            assert p.url_hash, f"url_hash empty for {p.url}"
            assert len(p.url_hash) == 64  # SHA-256 hex

    def test_engagement_metrics_positive(self) -> None:
        gen = SyntheticDataGenerator(count=20, seed=3)
        posts = gen.generate()
        for p in posts:
            assert p.followers >= 0
            assert p.upvotes >= 0
            assert p.comments >= 0

    def test_authors_populated(self) -> None:
        gen = SyntheticDataGenerator(count=10, seed=5)
        posts = gen.generate()
        for p in posts:
            assert p.author

    def test_scraped_at_populated(self) -> None:
        gen = SyntheticDataGenerator(count=5, seed=5)
        posts = gen.generate()
        for p in posts:
            assert p.scraped_at is not None


class TestFilterCalibration:
    """Posts should be calibrated to the real filter pipeline."""

    def test_some_posts_have_pain_keywords(self) -> None:
        """At least some posts should trigger keyword detection."""
        from radar.ranking.keywords import count_keyword_hits

        gen = SyntheticDataGenerator(count=50, seed=42)
        posts = gen.generate()
        hits = sum(
            1 for p in posts
            if count_keyword_hits(f"{p.title} {p.body}")
        )
        # At least 40% should have pain keywords (60% designed to pass + some non-maintainer)
        assert hits >= 20, f"Only {hits}/50 posts had pain keywords"

    def test_some_posts_have_maintainer_context(self) -> None:
        """At least some posts should have maintainer-context patterns."""
        from radar.ranking.keywords import MAINTAINER_PATTERNS

        gen = SyntheticDataGenerator(count=50, seed=42)
        posts = gen.generate()
        maintainer_hits = 0
        for p in posts:
            text = f"{p.title} {p.body}"
            if any(pat.search(text) for pat in MAINTAINER_PATTERNS):
                maintainer_hits += 1
        # ~60% designed to be maintainer posts
        assert maintainer_hits >= 15, f"Only {maintainer_hits}/50 had maintainer context"

    def test_mix_of_passing_and_failing_posts(self) -> None:
        """Not all posts should pass all filters — some should be noise."""
        from radar.ranking.filters import FilterPipeline

        gen = SyntheticDataGenerator(count=50, seed=42)
        posts = gen.generate()
        pipeline = FilterPipeline()
        filtered = pipeline.apply(posts)
        # Some pass, some don't — not 100% and not 0%
        assert 5 <= len(filtered) <= 45, (
            f"Expected 5-45 to pass filters, got {len(filtered)}/50"
        )


class TestPipelineIntegration:
    """Synthetic data should work through the full ranking pipeline."""

    def test_score_batch_succeeds(self) -> None:
        from radar.ranking.filters import FilterPipeline
        from radar.ranking.scorer import SignalScorer

        gen = SyntheticDataGenerator(count=30, seed=42)
        posts = gen.generate()

        filtered = FilterPipeline().apply(posts)
        assert len(filtered) > 0, "No posts passed filters"

        scorer = SignalScorer()
        scored = scorer.score_batch(filtered)
        assert len(scored) > 0
        # Scores should be positive
        for s in scored:
            assert s.final_score >= 0 or s.signal_score >= 0

    def test_end_to_end_with_storage(self, tmp_path) -> None:
        """Full round-trip: generate → filter → score → store → retrieve."""
        from radar.ranking.filters import FilterPipeline
        from radar.ranking.scorer import SignalScorer
        from radar.storage.database import Database

        db_path = str(tmp_path / "test_synth.db")
        db = Database(db_path)

        gen = SyntheticDataGenerator(count=30, seed=42)
        posts = gen.generate()
        filtered = FilterPipeline().apply(posts)
        scored = SignalScorer().score_batch(filtered)

        for post in scored[:5]:
            db.upsert_post(post)

        stats = db.get_stats()
        assert stats.get("post_count", 0) >= 1
