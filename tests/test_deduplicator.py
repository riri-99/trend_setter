"""Unit tests for SQLite deduplication and recency window checking."""

from datetime import datetime, timezone
from pathlib import Path
import pytest
from trend_copilot.ingestion.deduplicator import Deduplicator
from trend_copilot.ingestion.models import RawTrend
from trend_copilot.storage.db import get_connection


@pytest.fixture
def temp_db(tmp_path: Path):
    db_file = tmp_path / "test_agent.db"
    return db_file


def test_deduplicator_lifecycle(temp_db: Path):
    dedup = Deduplicator(db_path=temp_db, window_hours=48)

    trend = RawTrend(
        source="google_trends",
        title="Nvidia Stock Surge",
        summary="Nvidia shares reached all-time high.",
        url="https://finance.example.com/nvda",
        raw_score=100000.0,
        published_at=datetime.now(timezone.utc),
    )

    # 1. First time seeing trend: not a duplicate
    assert dedup.is_duplicate(trend) is False

    # 2. Record trend into SQLite
    row_id = dedup.record_trend(trend, status="qualified", velocity_score=80.0)
    assert row_id > 0

    # 3. Second check: should now be detected as duplicate
    assert dedup.is_duplicate(trend) is True

    # 4. Check that recent slugs includes it
    slugs = dedup.get_recent_slugs(hours=48)
    assert "nvidia-stock-surge" in slugs


def test_deduplicator_case_and_punctuation_insensitive(temp_db: Path):
    dedup = Deduplicator(db_path=temp_db, window_hours=48)

    t1 = RawTrend(
        source="reddit",
        title="OpenAI: Strawberry is Here!",
        raw_score=500.0,
        published_at=datetime.now(timezone.utc),
    )
    dedup.record_trend(t1)

    # Alternate casing and punctuation for same topic
    t2 = RawTrend(
        source="reddit",
        title="openai strawberry is here",
        raw_score=600.0,
        published_at=datetime.now(timezone.utc),
    )
    assert dedup.is_duplicate(t2) is True
