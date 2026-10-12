"""Unit tests for velocity scoring, controversy ratios, and cross-source fusion."""

from datetime import datetime, timedelta, timezone
from trend_copilot.ingestion.models import RawTrend
from trend_copilot.ingestion.scorer import (
    calculate_source_velocity,
    merge_cross_source_trends,
    score_candidate,
)


def test_google_velocity_calculation():
    pub = datetime.now(timezone.utc) - timedelta(hours=1)
    # High traffic: 200,000+
    high_t = RawTrend(
        source="google_trends",
        title="Major Tech Event",
        raw_score=200000.0,
        published_at=pub,
    )
    score_high = calculate_source_velocity(high_t)
    assert score_high == 100.0

    # Low traffic: 1,000
    low_t = RawTrend(
        source="google_trends",
        title="Minor Local Story",
        raw_score=1000.0,
        published_at=pub,
    )
    score_low = calculate_source_velocity(low_t)
    assert score_low < 1.0


def test_reddit_velocity_and_controversy():
    pub = datetime.now(timezone.utc) - timedelta(hours=1)

    # Standard post: 2000 upvotes, 200 comments
    normal_post = RawTrend(
        source="reddit",
        title="Cute Dog Playing",
        raw_score=2000.0,
        comment_count=200,
        published_at=pub,
    )
    normal_score = calculate_source_velocity(normal_post)

    # Highly controversial post: 500 upvotes, 2000 comments (flame war)
    controversial_post = RawTrend(
        source="reddit",
        title="Hot Take On Working Hours",
        raw_score=500.0,
        comment_count=2000,
        published_at=pub,
    )
    controversial_score = calculate_source_velocity(controversial_post)

    # Controversy bonus should push this to high velocity
    assert controversial_post.controversy_ratio > 1.0
    assert controversial_score > 90.0


def test_hackernews_velocity():
    pub = datetime.now(timezone.utc) - timedelta(hours=0.5)
    hn_story = RawTrend(
        source="hackernews",
        title="New Database Architecture",
        raw_score=250.0,
        comment_count=120,
        published_at=pub,
    )
    hn_score = calculate_source_velocity(hn_story)
    assert hn_score > 60.0


def test_merge_cross_source_trends():
    pub = datetime.now(timezone.utc)

    # Google Trends candidate
    g_trend = score_candidate(
        RawTrend(
            source="google_trends",
            title="Apple announces M5 chip",
            summary="Apple unveiled next generation M5 processor.",
            url="https://apple.com",
            raw_score=80000.0,
            published_at=pub,
        ),
        min_threshold=30.0,
    )

    # Reddit candidate for same news
    r_trend = score_candidate(
        RawTrend(
            source="reddit",
            title="Apple reveals new M5 processors with 30% performance boost",
            summary="Discussion in r/technology.",
            url="https://reddit.com/r/technology/m5",
            raw_score=1200.0,
            comment_count=450,
            published_at=pub,
        ),
        min_threshold=30.0,
    )

    # Hacker News candidate
    hn_trend = score_candidate(
        RawTrend(
            source="hackernews",
            title="Apple M5 Architecture Deep Dive",
            summary=None,
            url="https://news.ycombinator.com/item?id=999",
            raw_score=300.0,
            comment_count=80,
            published_at=pub,
        ),
        min_threshold=30.0,
    )

    merged = merge_cross_source_trends([g_trend, r_trend, hn_trend], threshold=70.0)

    # All three describe the Apple M5 launch and should be merged into 1 unified winner
    assert len(merged) == 1
    winner = merged[0]
    assert len(winner.cross_source_mentions) >= 2
    assert "google_trends" in winner.cross_source_mentions
