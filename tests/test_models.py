"""Unit tests for RawTrend, ScoredTrend, and slugification logic."""

from datetime import datetime, timedelta, timezone
from trend_copilot.ingestion.models import (
    RawTrend,
    ScoredTrend,
    compute_trend_hash,
    slugify_title,
)


def test_slugify_title():
    assert slugify_title("OpenAI Recalls Pin") == "openai-recalls-pin"
    assert slugify_title("  Apple M5 Chip: 2026!  ") == "apple-m5-chip-2026"
    assert slugify_title("What?? Is HAPPENING??") == "what-is-happening"
    assert slugify_title("") == "untitled"


def test_compute_trend_hash():
    h1 = compute_trend_hash("google_trends", "OpenAI Recalls Pin")
    h2 = compute_trend_hash("google_trends", "openai-recalls-pin")
    assert h1 == h2
    assert len(h1) == 32


def test_raw_trend_initialization():
    pub_time = datetime.now(timezone.utc) - timedelta(hours=2)
    trend = RawTrend(
        source="reddit",
        title="OpenAI launches Strawberry",
        summary="A new reasoning model has arrived.",
        url="https://reddit.com/r/technology/123",
        raw_score=1000.0,
        comment_count=250,
        published_at=pub_time,
    )

    assert trend.slug == "openai-launches-strawberry"
    assert trend.id != ""
    assert 1.9 <= trend.age_in_hours <= 2.1
    assert round(trend.controversy_ratio, 3) == round(250 / 1001.0, 3)


def test_scored_trend_inheritance():
    pub_time = datetime.now(timezone.utc)
    scored = ScoredTrend(
        source="hackernews",
        title="Show HN: A new compiler",
        raw_score=150.0,
        comment_count=45,
        published_at=pub_time,
        velocity_score=85.0,
        is_breaking=True,
        status="qualified",
    )

    assert scored.velocity_score == 85.0
    assert scored.is_breaking is True
    assert scored.status == "qualified"
    assert scored.category_hint == "general"
