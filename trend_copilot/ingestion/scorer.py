"""Velocity index calculation, controversy analysis, and cross-source fusion.

Normalizes engagement metrics across Google Trends, Reddit, and Hacker News
onto a standardized 0-100 Velocity Index, evaluates debate intensity, and
uses fuzzy string matching to merge stories breaking concurrently across platforms.
"""

from typing import Dict, List, Optional, Tuple
from rapidfuzz import fuzz
from trend_copilot.config import settings
from .models import RawTrend, ScoredTrend


def calculate_source_velocity(trend: RawTrend) -> float:
    """Calculate the normalized velocity score (0.0 to 100.0) based on source-specific dynamics.

    Google Trends:
        Volume-based: min(100, approx_traffic / 2000)

    Reddit:
        Velocity-based: min(100, (upvotes / (age_in_hours + 0.5) * 0.2) + (comments * 0.1))

    Hacker News:
        Speed-based: min(100, (score / (age_in_hours + 0.5) * 0.5))
    """
    age = trend.age_in_hours
    source = trend.source.lower()

    if "google" in source:
        # approx_traffic is in raw_score
        traffic = max(0.0, trend.raw_score)
        score = min(100.0, traffic / 2000.0)
        # Recency boost if published in last 2 hours
        if age <= 2.0 and score > 0:
            score = min(100.0, score * 1.15)
        return round(score, 2)

    elif "reddit" in source:
        upvotes = max(0.0, trend.raw_score)
        comments = max(0, trend.comment_count)
        time_factor = age + 0.5
        upvote_velocity = (upvotes / time_factor) * 0.2
        comment_velocity = comments * 0.1
        total = upvote_velocity + comment_velocity

        # Controversy bonus if comments exceed 25% of upvotes
        controversy = trend.controversy_ratio
        if controversy > 0.25:
            total += min(15.0, controversy * 20.0)

        return round(min(100.0, max(0.0, total)), 2)

    elif "hacker" in source or "hn" in source:
        hn_score = max(0.0, trend.raw_score)
        time_factor = age + 0.5
        points_velocity = (hn_score / time_factor) * 0.5
        # Comment engagement boost
        comments = max(0, trend.comment_count)
        comments_boost = min(15.0, comments * 0.2)
        total = points_velocity + comments_boost
        return round(min(100.0, max(0.0, total)), 2)

    else:
        # Fallback generic velocity
        raw = max(0.0, trend.raw_score)
        time_factor = age + 0.5
        score = (raw / time_factor) * 0.3
        return round(min(100.0, max(0.0, score)), 2)


def score_candidate(trend: RawTrend, min_threshold: Optional[float] = None) -> ScoredTrend:
    """Evaluate and convert a RawTrend into a ScoredTrend candidate."""
    threshold = min_threshold if min_threshold is not None else settings.MIN_VELOCITY_SCORE
    velocity = calculate_source_velocity(trend)
    is_breaking = velocity >= 75.0 and trend.age_in_hours <= 2.0

    if velocity >= threshold:
        status = "qualified"
        rejection_reason = None
    else:
        status = "dropped_low_velocity"
        rejection_reason = f"Velocity {velocity:.1f} below threshold {threshold:.1f}"

    return ScoredTrend(
        id=trend.id,
        source=trend.source,
        title=trend.title,
        summary=trend.summary,
        url=trend.url,
        raw_score=trend.raw_score,
        comment_count=trend.comment_count,
        published_at=trend.published_at,
        fetched_at=trend.fetched_at,
        category_hint=trend.category_hint,
        slug=trend.slug,
        velocity_score=velocity,
        is_breaking=is_breaking,
        status=status,
        rejection_reason=rejection_reason,
        cross_source_mentions=[trend.source],
    )


STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "with",
    "by", "from", "is", "are", "was", "were", "new", "how", "why", "what",
    "reveals", "announces", "announced", "unveils", "unveiled", "launches", "launched"
}


def are_trends_similar(
    title_a: str,
    title_b: str,
    threshold: Optional[float] = None
) -> bool:
    """Determine whether two trend titles refer to the same event.

    Combines RapidFuzz WRatio / token_set_ratio with significant entity/keyword
    containment matching to recognize breaking stories worded differently.
    """
    sim_threshold = threshold if threshold is not None else settings.SIMILARITY_THRESHOLD

    # 1. Fuzzy string matching
    w_ratio = fuzz.WRatio(title_a, title_b)
    ts_ratio = fuzz.token_set_ratio(title_a, title_b)
    if max(w_ratio, ts_ratio) >= sim_threshold:
        return True

    # 2. Significant keyword / entity containment (Jaccard-like check)
    import re
    tokens_a = set(re.findall(r"\b\w{2,}\b", title_a.lower())) - STOPWORDS
    tokens_b = set(re.findall(r"\b\w{2,}\b", title_b.lower())) - STOPWORDS

    if tokens_a and tokens_b:
        intersection = tokens_a & tokens_b
        min_len = min(len(tokens_a), len(tokens_b))
        overlap_pct = (len(intersection) / min_len) * 100.0
        # If at least 2 significant keywords match and cover >= 50% of the shorter title
        if len(intersection) >= 2 and overlap_pct >= 50.0:
            return True

    return False


def merge_cross_source_trends(
    trends: List[ScoredTrend],
    threshold: Optional[float] = None
) -> List[ScoredTrend]:
    """Cluster and merge candidate trends across different data sources.

    When both Google Trends and Reddit or HN report the same breaking story:
    1. Cross-source mentions are tracked.
    2. A multi-platform momentum boost (+15 velocity points) is applied.
    3. The richest summary and primary link are retained.
    """
    if not trends:
        return []

    merged: List[ScoredTrend] = []

    for candidate in sorted(trends, key=lambda t: t.velocity_score, reverse=True):
        matched = False
        for existing in merged:
            if are_trends_similar(existing.title, candidate.title, threshold):
                # Found cross-source match!
                matched = True
                # Add cross-source attribution if distinct
                if candidate.source not in existing.cross_source_mentions:
                    existing.cross_source_mentions.append(candidate.source)
                    # Multi-source momentum boost (+15 points, max 100)
                    existing.velocity_score = min(100.0, round(existing.velocity_score + 15.0, 2))

                # Combine summary if candidate offers richer information
                if (not existing.summary or len(existing.summary) < 50) and candidate.summary:
                    existing.summary = candidate.summary

                # If existing lacks URL, borrow candidate URL
                if not existing.url and candidate.url:
                    existing.url = candidate.url

                # If either is breaking, flag merged as breaking
                if candidate.is_breaking:
                    existing.is_breaking = True
                break

        if not matched:
            merged.append(candidate)

    return merged
