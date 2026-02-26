"""Keyword patterns and PainCategory weights for signal detection."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from radar.models import PainCategory

# ---------------------------------------------------------------------------
# Each entry is (pattern_string, weight) where weight ∈ [1.0, 3.0]
# ---------------------------------------------------------------------------

_RAW_PATTERNS: Dict[PainCategory, List[Tuple[str, float]]] = {
    PainCategory.BURNOUT: [
        (r"\bburnou?t\b", 3.0),
        (r"\bburnt\b", 3.0),
        (r"\bburned?\s+out\b", 3.0),
        (r"\bexhausted?\b", 2.5),
        (r"\bquitting\b", 2.5),
        (r"\bstepping down\b", 2.5),
        (r"\bgiving up\b", 2.0),
        (r"\bno longer maintain", 3.0),
        (r"\btoo tired\b", 2.0),
        (r"\bmentally drained\b", 2.5),
        (r"\bunpaid work\b", 2.0),
        (r"\bsolo maintainer\b", 2.0),
        (r"\bworn out\b", 2.0),
        (r"\boverwhel", 2.0),
        (r"\bno time\b", 1.5),
        (r"\bfree time\b", 1.5),
    ],
    PainCategory.FUNDING: [
        (r"\bfunding\b", 2.5),
        (r"\bsustainab", 2.5),
        (r"\bdonat", 2.0),
        (r"\bsponsorship\b", 2.0),
        (r"\bopen collective\b", 2.0),
        (r"\bgithub sponsors\b", 2.0),
        (r"\bpatreon\b", 1.5),
        (r"\bno budget\b", 2.5),
        (r"\bunfunded\b", 2.5),
        (r"\bvolunteer work\b", 2.0),
        (r"\bfinancially\b", 1.5),
        (r"\bpaid maintainer\b", 2.0),
        (r"\bfull[ -]time oss\b", 2.5),
        (r"\bmonetary support\b", 2.0),
    ],
    PainCategory.TOXIC_USERS: [
        (r"\btoxic\b", 3.0),
        (r"\bharassment\b", 3.0),
        (r"\babusive user", 3.0),
        (r"\bentitled user", 2.5),
        (r"\brude\b", 2.0),
        (r"\bdisrespect", 2.5),
        (r"\binsult", 2.0),
        (r"\baggressive comment", 2.5),
        (r"\bnasty\b", 2.0),
        (r"\bdemanding user", 2.5),
        (r"\bthreat", 2.0),
        (r"\bhostile", 2.0),
    ],
    PainCategory.MAINTENANCE_BURDEN: [
        (r"\bmaintenance burden\b", 3.0),
        (r"\btoo many issues\b", 2.0),
        (r"\bpr backlog\b", 2.5),
        (r"\bpull request backlog\b", 2.5),
        (r"\bissue backlog\b", 2.0),
        (r"\blegacy code\b", 2.0),
        (r"\btechnical debt\b", 2.5),
        (r"\brefactor\b", 1.5),
        (r"\buntestable\b", 2.0),
        (r"\bhard to maintain\b", 2.5),
        (r"\bbox of entropy\b", 1.5),
        (r"\bnobody reviews\b", 2.0),
        (r"\bstale pr\b", 2.0),
        (r"\bbandaid fix\b", 1.5),
        (r"\bmemory leak\b", 2.5),
        (r"\bperformance regression\b", 2.5),
        (r"\bregression\b", 2.0),
    ],
    PainCategory.DEPENDENCY_HELL: [
        (r"\bdependency hell\b", 3.0),
        (r"\bdep conflict\b", 2.5),
        (r"\bdependency conflicts?\b", 2.5),
        (r"\bbroken dependency\b", 2.5),
        (r"\bupper bound\b", 2.0),
        (r"\bversion pinning\b", 2.0),
        (r"\bdiamond dependency\b", 3.0),
        (r"\btransitive dep", 2.0),
        (r"\bincompatible ver", 2.0),
        (r"\bdependabot\b", 1.5),
        (r"\brenovate\b", 1.5),
        (r"\bpeer dep", 2.0),
        (r"\b(npm|pip|cargo|maven) install fail", 2.5),
        (r"\bdependency audit\b", 2.5),
        (r"\bdependency management\b", 2.0),
    ],
    PainCategory.SECURITY_PRESSURE: [
        (r"\bsecurity vulner", 3.0),
        (r"\bvulnerabilit", 2.5),
        (r"\bcve-\d{4}", 3.0),
        (r"\bsecurity patch\b", 2.5),
        (r"\bsecurity audit\b", 2.5),
        (r"\bsecurity disclosure\b", 2.5),
        (r"\bresponsible disclos", 2.5),
        (r"\bzero[ -]day\b", 3.0),
        (r"\brce\b", 3.0),
        (r"\bsecurity report\b", 2.5),
        (r"\bsupply chain attack\b", 3.0),
        (r"\bmalicious package\b", 3.0),
        (r"\btyposquat", 2.5),
        (r"\bsast\b", 2.0),
        (r"\bsnyk\b", 1.5),
    ],
    PainCategory.BREAKING_CHANGES: [
        (r"\bbreaking changes?\b", 3.0),
        (r"\bbreaking api\b", 2.5),
        (r"\bapi breaking\b", 2.5),
        (r"\bbreaking.*changes\b", 2.5),
        (r"\bbc\b", 1.0),
        (r"\bapi break", 2.5),
        (r"\bapi.*change", 2.0),
        (r"\bdeprecated\b", 2.0),
        (r"\bmajor version\b", 2.0),
        (r"\bsemver\b", 1.5),
        (r"\bbackward compat", 2.5),
        (r"\bbackwards compat", 2.5),
        (r"\bremoved in v\d", 2.5),
        (r"\bremoved api\b", 2.5),
        (r"\bmigration guide\b", 2.0),
        (r"\bupgrade guide\b", 2.0),
        (r"\bno longer support", 2.5),
    ],
    PainCategory.DOCUMENTATION: [
        (r"\bdocumentation\b", 2.0),
        (r"\bdocs are\b", 2.0),
        (r"\bpoor docs\b", 2.5),
        (r"\bno docs\b", 3.0),
        (r"\bmissing docs\b", 2.5),
        (r"\bwrong docs\b", 2.5),
        (r"\bstale docs\b", 2.5),
        (r"\bno readme\b", 2.5),
        (r"\bno example", 2.0),
        (r"\bconfusing docs\b", 2.5),
        (r"\bhard to understand\b", 2.0),
        (r"\bwhere is the docs\b", 2.0),
        (r"\bcan'?t find doc", 2.0),
    ],
    PainCategory.CONTRIBUTOR_FRICTION: [
        (r"\bcontribut", 2.0),
        (r"\bfirst pr\b", 1.5),
        (r"\bno contributors\b", 2.5),
        (r"\bcontribution guide\b", 2.0),
        (r"\bcontribut.*barrier\b", 3.0),
        (r"\bhigh barrier\b", 2.5),
        (r"\bdev setup\b", 1.5),
        (r"\bdev environment\b", 1.5),
        (r"\bwelcoming community\b", 1.5),
        (r"\bignored pr\b", 2.5),
        (r"\bgood first issue\b", 1.5),
        (r"\bno review\b", 2.0),
    ],
    PainCategory.CORPORATE_EXPLOITATION: [
        (r"\bcorporate exploit", 3.0),
        (r"\bfree rider\b", 2.5),
        (r"\bfree[ -]riding\b", 2.5),
        (r"\bexploit.*open source\b", 3.0),
        (r"\bno contribution back\b", 2.5),
        (r"\bnot giving back\b", 2.5),
        (r"\bbig (company|corp|tech).*use\b", 2.0),
        (r"\bno upstream\b", 2.0),
        (r"\blicens.*violat", 3.0),
        (r"\bsla.*oss\b", 2.0),
        (r"\bwhite[ -]label\b", 2.0),
        (r"\bsteal.*code\b", 3.0),
    ],
    PainCategory.SCOPE_CREEP: [
        (r"\bscope creep\b", 3.0),
        (r"\bfeature creep\b", 3.0),
        (r"\btoo many features\b", 2.5),
        (r"\bbloat\b", 2.0),
        (r"\bfeature request flood\b", 2.5),
        (r"\bnot designed for\b", 2.0),
        (r"\bout of scope\b", 2.5),
        (r"\bdo one thing\b", 1.5),
        (r"\bfeature fatigue\b", 2.5),
        (r"\bunix philosophy\b", 1.5),
    ],
    PainCategory.TOOLING_FATIGUE: [
        (r"\btooling fatigue\b", 3.0),
        (r"\bbuild tool", 1.5),
        (r"\bbuild tooling\b", 2.0),
        (r"\bci[ /]cd\b", 1.5),
        (r"\bgithub actions\b", 1.5),
        (r"\bflaky test", 2.5),
        (r"\bci.*fail", 2.0),
        (r"\bbuild.*fail", 2.0),
        (r"\bbroken build\b", 2.5),
        (r"\binfrastructure cost\b", 2.5),
        (r"\bcloud cost\b", 2.0),
        (r"\bpipeline\b", 1.5),
        (r"\btoo many tools\b", 2.5),
        (r"\bpackage manager hell\b", 2.5),
        (r"\btest coverage\b", 2.0),
        (r"\brelease process\b", 2.0),
        (r"\brelease.*pain\b", 2.5),
    ],
    PainCategory.GOVERNANCE: [
        (r"\bgovernance\b", 2.5),
        (r"\bcode of conduct\b", 2.0),
        (r"\bproject direction\b", 2.0),
        (r"\bbenevolent dict", 2.5),
        (r"\bbdfl\b", 2.5),
        (r"\bdecision making\b", 2.0),
        (r"\bfork\b", 1.5),
        (r"\bcore team\b", 1.5),
        (r"\bsteering commit", 2.0),
        (r"\bdispute\b", 2.0),
        (r"\bcontro?vers", 2.0),
    ],
    PainCategory.ABUSE: [
        (r"\babuse\b", 3.0),
        (r"\bspam\b", 2.5),
        (r"\bbot attack\b", 2.5),
        (r"\btroll\b", 2.5),
        (r"\bmalicious\b", 2.5),
        (r"\bdmca\b", 2.5),
        (r"\bcopyright claim\b", 2.5),
        (r"\blagal threat\b", 2.5),
        (r"\blegal.*threat\b", 2.5),
        (r"\blitigat\b", 2.5),
    ],
    PainCategory.CI_CD: [
        (r"\bci[/ _-]?cd\b", 2.5),
        (r"\bcontinuous integrat", 2.0),
        (r"\bcontinuous deliver", 2.0),
        (r"\bpipeline.*fail", 2.5),
        (r"\bfailed.*pipeline\b", 2.5),
        (r"\bgithub actions.*fail", 2.5),
        (r"\bflaky.*ci\b", 2.5),
        (r"\bci.*broken\b", 2.5),
        (r"\bdeploy.*fail", 2.0),
        (r"\brelease.*fail", 2.0),
        (r"\btest.*fail\b", 2.0),
        (r"\bbuild.*fail\b", 2.0),
        (r"\bnightly.*fail", 2.0),
    ],
}

# ---------------------------------------------------------------------------
# Compile all patterns once at module load time
# ---------------------------------------------------------------------------

COMPILED_PATTERNS: Dict[PainCategory, List[Tuple[re.Pattern[str], float]]] = {
    category: [
        (re.compile(pattern, re.IGNORECASE | re.DOTALL), weight)
        for pattern, weight in patterns
    ]
    for category, patterns in _RAW_PATTERNS.items()
}

# Per-category base score multipliers (used by scorer)
PAIN_FACTORS: Dict[PainCategory, float] = {
    PainCategory.BURNOUT: 1.5,
    PainCategory.ABUSE: 1.5,
    PainCategory.SECURITY_PRESSURE: 1.4,
    PainCategory.TOXIC_USERS: 1.4,
    PainCategory.CORPORATE_EXPLOITATION: 1.3,
    PainCategory.DEPENDENCY_HELL: 1.2,
    PainCategory.CI_CD: 1.2,
    PainCategory.BREAKING_CHANGES: 1.2,
    PainCategory.FUNDING: 1.3,
    PainCategory.GOVERNANCE: 1.2,
    PainCategory.MAINTENANCE_BURDEN: 1.2,
    PainCategory.CONTRIBUTOR_FRICTION: 1.1,
    PainCategory.DOCUMENTATION: 1.1,
    PainCategory.SCOPE_CREEP: 1.1,
    PainCategory.TOOLING_FATIGUE: 1.0,
}

# ---------------------------------------------------------------------------
# Maintainer context patterns (Layer 2 filter)
# ---------------------------------------------------------------------------

_MAINTAINER_RAW: List[str] = [
    r"\bmy repo\b",
    r"\bmy project\b",
    r"\bi maintain\b",
    r"\bwe maintain\b",
    r"\bour library\b",
    r"\bi'?m the author\b",
    r"\bi released\b",
    r"\bour maintainers?\b",
    r"\bpull request\b",
    r"\bmerged\b",
    r"\bopened an issue\b",
    r"\breleased v\d",
    r"\bas (the|a) maintainer\b",
    r"\bsole maintainer\b",
    r"\bproject maintainer\b",
    r"\bi authored\b",
    r"\bmy library\b",
    r"\bmy package\b",
    r"\bmy crate\b",
    r"\bmy gem\b",
    r"\bi created\b",
    r"\bwe released\b",
    r"\bour project\b",
    r"\bour repo\b",
    r"\bwe published\b",
    r"\bi published\b",
]

MAINTAINER_PATTERNS: List[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE | re.DOTALL) for p in _MAINTAINER_RAW
]


def count_keyword_hits(text: str) -> Dict[PainCategory, float]:
    """Return weighted hit counts per PainCategory for *text*.

    Returns an empty dict if no patterns match.
    """
    results: Dict[PainCategory, float] = {}
    for category, compiled in COMPILED_PATTERNS.items():
        total_weight = 0.0
        for pattern, weight in compiled:
            if pattern.search(text):
                total_weight += weight
        if total_weight > 0:
            results[category] = total_weight
    return results
