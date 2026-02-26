"""Synthetic data generator for end-to-end pipeline testing without API keys."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import List, Optional

from radar.models import PainCategory, RawPost
from radar.ranking.keywords import _MAINTAINER_RAW, _RAW_PATTERNS


# ---------------------------------------------------------------------------
# Pain-themed post templates — each tuple is (title, body_template, categories)
# Body templates contain {keyword} placeholders filled from the real keyword list.
# ---------------------------------------------------------------------------

_TEMPLATES: list[tuple[str, str, list[PainCategory]]] = [
    (
        "I'm mass-closing issues in my project because burnout is real",
        "After 6 years as sole maintainer of this library, I'm {keyword}. "
        "I maintain this in my free time and the maintenance burden is crushing. "
        "No funding, no help, just a wall of entitled users.",
        [PainCategory.BURNOUT, PainCategory.MAINTENANCE_BURDEN],
    ),
    (
        "Our dependency hell just broke the entire CI pipeline",
        "Spent all weekend debugging {keyword}. The transitive dependency conflict "
        "between v3 and v5 caused our nightly builds to fail. Released v2.1 "
        "yesterday and now everything is broken.",
        [PainCategory.DEPENDENCY_HELL, PainCategory.CI_CD],
    ),
    (
        "Security vulnerability disclosure process is a nightmare",
        "I released v4.2 last week with a security patch for a {keyword}. "
        "As the maintainer of this project, I had to handle the responsible "
        "disclosure with zero support. The CVE-2026 process is painful.",
        [PainCategory.SECURITY_PRESSURE],
    ),
    (
        "Breaking changes in upstream are destroying our ecosystem",
        "My library depends on 3 packages that all shipped {keyword} in the "
        "same month. I maintain backwards compatibility for 200+ downstream "
        "users and the migration guide is a mess.",
        [PainCategory.BREAKING_CHANGES, PainCategory.DEPENDENCY_HELL],
    ),
    (
        "Toxic users are why maintainers quit",
        "Another day, another {keyword} comment on my repo. I'm the author "
        "of a popular package and the entitlement is overwhelming. "
        "People demanding features while contributing nothing back.",
        [PainCategory.TOXIC_USERS, PainCategory.CORPORATE_EXPLOITATION],
    ),
    (
        "Open source funding model is fundamentally broken",
        "We maintain critical infrastructure used by Fortune 500 companies. "
        "Our {keyword} campaign raised $200/month. Meanwhile big tech "
        "uses our library in production with zero contribution back.",
        [PainCategory.FUNDING, PainCategory.CORPORATE_EXPLOITATION],
    ),
    (
        "CI/CD pipeline flakiness is killing developer productivity",
        "Our GitHub Actions workflow has been {keyword} for 3 weeks. "
        "Flaky tests, random timeouts, and build failures are making "
        "merged PRs a gamble. The test suite takes 45 minutes.",
        [PainCategory.CI_CD, PainCategory.TOOLING_FATIGUE],
    ),
    (
        "Documentation debt is the silent killer of open source projects",
        "I maintain a popular library with {keyword}. New contributors "
        "keep asking the same questions because our docs are stale. "
        "Nobody reviews documentation PRs.",
        [PainCategory.DOCUMENTATION, PainCategory.CONTRIBUTOR_FRICTION],
    ),
    (
        "Governance crisis in our open source foundation",
        "The {keyword} in our project has escalated. As a maintainer, "
        "I've watched the core team fragment over licensing decisions. "
        "The steering committee can't agree on the project direction.",
        [PainCategory.GOVERNANCE, PainCategory.ABUSE],
    ),
    (
        "Feature scope creep is making our library unmaintainable",
        "My project started as a simple utility but {keyword} has turned "
        "it into a bloated mess. Every PR adds features nobody asked for. "
        "The release process is now a week-long ordeal.",
        [PainCategory.SCOPE_CREEP, PainCategory.MAINTENANCE_BURDEN],
    ),
]

# Templates that will FAIL the maintainer-context filter (no first-person maintainer voice)
_NON_MAINTAINER_TEMPLATES: list[tuple[str, str, list[PainCategory]]] = [
    (
        "Why is npm install so slow these days?",
        "Every time I try to install a package, {keyword} happens. "
        "The ecosystem is getting worse. Is anyone else seeing this?",
        [PainCategory.DEPENDENCY_HELL],
    ),
    (
        "Generic tech complaints thread",
        "Software engineering has become all about {keyword}. "
        "The tools keep changing and nothing works well together.",
        [PainCategory.TOOLING_FATIGUE],
    ),
]

# Templates that will FAIL the keyword filter (no pain keywords)
_NO_PAIN_TEMPLATES: list[tuple[str, str, list[PainCategory]]] = [
    (
        "Check out my new side project!",
        "I just shipped a cool new tool that helps with project management. "
        "Built with Rust and it's blazingly fast. Star it on GitHub!",
        [],
    ),
    (
        "Happy to announce our v3.0 release",
        "Exciting times! We've been working hard and the new version is "
        "packed with improvements. Thanks to all our amazing contributors.",
        [],
    ),
]

PLATFORMS = ["reddit", "hackernews", "devto", "lobsters"]

_AUTHORS = [
    "oxide_dev", "async_sam", "cargo_queen", "pip_wizard", "nix_nomad",
    "kernel_karen", "npm_ninja", "rust_ranger", "go_guru", "ci_chad",
    "devops_diana", "patch_pete", "merge_mia", "lint_larry", "test_tara",
]


def _pick_keyword(category: PainCategory, rng: random.Random) -> str:
    """Pick a representative keyword phrase from the real pattern registry."""
    patterns = _RAW_PATTERNS.get(category, [])
    if not patterns:
        return "technical challenges"
    # Extract human-readable text from regex patterns
    raw_pattern, _ = rng.choice(patterns)
    # Strip regex anchors/metacharacters to get readable text
    text = raw_pattern.replace(r"\b", "").replace(r"\s+", " ")
    text = text.replace("?", "").replace("(", "").replace(")", "")
    text = text.replace("[/ _-]", " ").replace("[ -]", " ")
    text = text.replace(".*", " ").replace(r"\d{4}", "2026")
    text = text.replace(r"\d", "1").replace("s?", "s")
    return text.strip()


class SyntheticDataGenerator:
    """Generate realistic fake RawPost data for end-to-end pipeline testing.

    Uses real pain keywords and maintainer patterns from the ranking module
    to ensure synthetic posts are calibrated to the actual filter logic.

    Args:
        count: Number of posts to generate (default 50).
        seed: Random seed for reproducibility (default None = random).
    """

    def __init__(self, count: int = 50, seed: Optional[int] = None) -> None:
        self.count = count
        self.seed = seed
        self._rng = random.Random(seed)

    def generate(self) -> List[RawPost]:
        """Generate a batch of synthetic posts.

        Approximately:
        - 60% pass all 3 filter layers (keyword + maintainer + sentiment)
        - 15% fail maintainer-context filter
        - 15% fail keyword filter (no pain keywords)
        - 10% pass filters but with positive sentiment (filtered by sentiment gate)

        All 4 platforms are represented roughly equally.
        """
        posts: List[RawPost] = []
        now = datetime.utcnow()

        for i in range(self.count):
            platform = PLATFORMS[i % len(PLATFORMS)]
            author = self._rng.choice(_AUTHORS)

            # Decide which category this post falls into
            bucket = self._rng.random()

            if bucket < 0.60:
                # Full pass: pain keyword + maintainer context + negative sentiment
                template = self._rng.choice(_TEMPLATES)
                post = self._build_from_template(
                    idx=i, template=template, platform=platform,
                    author=author, now=now, negative=True,
                )
            elif bucket < 0.75:
                # Fail: no maintainer context
                template = self._rng.choice(_NON_MAINTAINER_TEMPLATES)
                post = self._build_from_template(
                    idx=i, template=template, platform=platform,
                    author=author, now=now, negative=True,
                )
            elif bucket < 0.90:
                # Fail: no pain keywords
                template = self._rng.choice(_NO_PAIN_TEMPLATES)
                post = self._build_from_template(
                    idx=i, template=template, platform=platform,
                    author=author, now=now, negative=False,
                )
            else:
                # Fail: positive sentiment (will be caught by sentiment gate)
                template = self._rng.choice(_TEMPLATES)
                post = self._build_from_template(
                    idx=i, template=template, platform=platform,
                    author=author, now=now, negative=False,
                    force_positive=True,
                )

            posts.append(post)

        return posts

    def _build_from_template(
        self,
        idx: int,
        template: tuple[str, str, list[PainCategory]],
        platform: str,
        author: str,
        now: datetime,
        negative: bool = True,
        force_positive: bool = False,
    ) -> RawPost:
        title_tpl, body_tpl, categories = template

        # Pick a real keyword to fill the template
        if categories:
            keyword = _pick_keyword(self._rng.choice(categories), self._rng)
        else:
            keyword = "productivity tools"

        body = body_tpl.format(keyword=keyword)

        if force_positive:
            body = f"This is amazing! Great progress. {body}. Love this community!"
            title = f"🎉 {title_tpl}"
        else:
            title = title_tpl

        # Generate varied engagement metrics
        followers = self._rng.randint(50, 100_000)
        upvotes = self._rng.randint(5, 2000)
        comments = self._rng.randint(1, 500)

        # Post age: 0-23 hours ago (within daily scrape window)
        hours_ago = self._rng.uniform(0.5, 23.0)
        created = now - timedelta(hours=hours_ago)
        scraped = now - timedelta(minutes=self._rng.randint(1, 30))

        url = f"https://{platform}.example.com/post/synth-{idx:04d}"

        return RawPost(
            url=url,
            title=title,
            body=body,
            platform=platform,
            author=author,
            followers=followers,
            author_karma=followers,
            upvotes=upvotes,
            score=upvotes,
            comments=comments,
            comment_count=comments,
            tags=[c.value for c in categories[:3]],
            scraped_at=scraped,
            created_utc=created,
        )
