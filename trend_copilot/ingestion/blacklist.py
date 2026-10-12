"""Safety and tragedy blacklist filter for pre-LLM candidate screening.

Screens trend titles and news summaries against regular expression patterns
covering fatal casualties, geopolitical armed conflicts, severe violence,
and health crises to guarantee zero inappropriate satire.
"""

import re
from typing import Dict, List, Optional, Tuple
from .models import RawTrend


# Granular category definitions of sensitive and tragic terms
SAFETY_CATEGORIES: Dict[str, List[str]] = {
    "casualties_accidents": [
        r"\b(killed|died|dead|death|fatal|fatalities|casualt\w*|massacre|plane crash|car crash)\b",
        r"\b(drown\w*|train derailment|building collapse|explosion|suicide|overdose)\b",
        r"\b(mourning|funeral|victim\w*|autopsy)\b",
    ],
    "war_and_terrorism": [
        r"\b(war|warfare|airstrike|bombing|hostage|terrorist|terrorism|genocide|missile strike)\b",
        r"\b(invasion|battlefield|insurgency|ceasefire violation|artillery shell\w*)\b",
    ],
    "health_and_disease": [
        r"\b(epidemic|pandemic|ebola|outbreak|cancer diagnosis|terminal illness)\b",
        r"\b(quarantine|intensive care unit|icu admission|coma)\b",
    ],
    "violence_and_crimes": [
        r"\b(shooting|active shooter|mass shooting|homicide|murder\w*|assault\w*)\b",
        r"\b(sexual abuse|rape|trafficking|pedophile|child abuse|kidnap\w*|abduct\w*)\b",
    ],
}

# Pre-compile regexes for optimal throughput
COMPILED_PATTERNS: List[Tuple[str, re.Pattern]] = [
    (category, re.compile(pattern, re.IGNORECASE))
    for category, patterns in SAFETY_CATEGORIES.items()
    for pattern in patterns
]


def check_safety(text: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Scan text against the safety blacklist patterns.

    Args:
        text: String to evaluate (title, description, or comment body).

    Returns:
        Tuple of (is_safe: bool, triggered_category: Optional[str], matched_text: Optional[str])
    """
    if not text:
        return True, None, None

    for category, pattern in COMPILED_PATTERNS:
        match = pattern.search(text)
        if match:
            return False, category, match.group(0)

    return True, None, None


def evaluate_trend_safety(trend: RawTrend) -> Tuple[bool, Optional[str]]:
    """Evaluate both title and summary of a RawTrend candidate.

    Args:
        trend: The RawTrend instance.

    Returns:
        Tuple of (is_safe: bool, reason: Optional[str])
    """
    # 1. Check title
    safe, category, matched = check_safety(trend.title)
    if not safe:
        return False, f"Title matched {category}: '{matched}'"

    # 2. Check summary / selftext if present
    if trend.summary:
        safe, category, matched = check_safety(trend.summary)
        if not safe:
            return False, f"Summary matched {category}: '{matched}'"

    return True, None
