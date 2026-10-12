"""Unit tests for the IngestionPipeline end-to-end coordinator."""

from datetime import datetime, timezone
from pathlib import Path
from typing import List
import pytest
from trend_copilot.ingestion.collectors.base import BaseCollector
from trend_copilot.ingestion.deduplicator import Deduplicator
from trend_copilot.ingestion.models import RawTrend
from trend_copilot.ingestion.pipeline import IngestionPipeline


class MockCollector(BaseCollector):
    """Mock collector yielding pre-defined test trends."""

    def __init__(self, name: str, items: List[RawTrend]) -> None:
        self._name = name
        self._items = items

    @property
    def source_name(self) -> str:
        return self._name

    async def fetch_trends(self) -> List[RawTrend]:
        return self._items


@pytest.mark.asyncio
async def test_pipeline_filtering_and_merging_lifecycle(tmp_path: Path):
    db_file = tmp_path / "test_pipeline.db"
    dedup = Deduplicator(db_path=db_file, window_hours=48)
    now = datetime.now(timezone.utc)

    # Pre-record an existing trend into the database to test Tier 2 Deduplication
    old_trend = RawTrend(
        source="google_trends",
        title="Yesterday's Big News",
        raw_score=100000.0,
        published_at=now,
    )
    dedup.record_trend(old_trend, status="qualified")

    # Mock trends for current cycle:
    # 1. Tragic topic (Tier 1 drop)
    t_tragedy = RawTrend(
        source="google_trends",
        title="Fatal earthquake disaster reported with casualties",
        raw_score=150000.0,
        published_at=now,
    )

    # 2. Duplicate topic (Tier 2 drop)
    t_duplicate = RawTrend(
        source="reddit",
        title="yesterdays big news",
        raw_score=2000.0,
        published_at=now,
    )

    # 3. Low velocity topic (Tier 3 drop)
    t_low_vel = RawTrend(
        source="google_trends",
        title="Local bake sale competition",
        raw_score=100.0,
        published_at=now,
    )

    # 4. High-velocity topic Source A (Apple M5)
    t_high_a = RawTrend(
        source="google_trends",
        title="Apple announces M5 chip",
        summary="Apple silicon next gen M5 chip announced.",
        url="https://apple.com/m5",
        raw_score=180000.0,
        published_at=now,
    )

    # 5. High-velocity topic Source B (Matching Apple M5)
    t_high_b = RawTrend(
        source="hackernews",
        title="Apple M5 Chip unveiled with next-gen neural cores",
        summary="HN discussion on M5 architecture.",
        url="https://news.ycombinator.com/item?id=888",
        raw_score=350.0,
        comment_count=120,
        published_at=now,
    )

    collector_a = MockCollector("google_trends", [t_tragedy, t_low_vel, t_high_a])
    collector_b = MockCollector("hackernews", [t_duplicate, t_high_b])

    pipeline = IngestionPipeline(
        collectors=[collector_a, collector_b],
        deduplicator=dedup,
        min_velocity=60.0,
        top_limit=5,
    )

    result = await pipeline.run()

    # Total items fetched: 5
    assert result.total_fetched == 5

    # 1 dropped by safety blacklist
    assert result.dropped_safety == 1

    # 1 dropped by deduplicator
    assert result.dropped_duplicates == 1

    # 1 dropped by low velocity
    assert result.dropped_low_velocity == 1

    # 2 high-velocity items merged into 1 qualified winner
    assert result.qualified_count == 1
    winner = result.qualified_trends[0]
    assert "Apple" in winner.title
    assert "M5" in winner.title
    assert len(winner.cross_source_mentions) == 2
    assert "google_trends" in winner.cross_source_mentions
    assert "hackernews" in winner.cross_source_mentions
    assert winner.status == "qualified"
    assert winner.velocity_score >= 60.0
