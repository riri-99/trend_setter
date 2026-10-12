"""Unit tests for the pre-LLM safety and tragedy blacklist."""

from datetime import datetime, timezone
from trend_copilot.ingestion.blacklist import check_safety, evaluate_trend_safety
from trend_copilot.ingestion.models import RawTrend


def test_safe_topics_pass():
    safe_topics = [
        "Nintendo announces Switch 2 launch date",
        "OpenAI reveals new reasoning system",
        "Taylor Swift breaks Spotify streaming records",
        "Meta employees protest return to office mandate",
        "Tesla releases robotaxi update in California",
    ]
    for topic in safe_topics:
        is_safe, category, matched = check_safety(topic)
        assert is_safe is True, f"Expected safe topic '{topic}' to pass, but triggered {category}"


def test_tragedy_topics_fail():
    unsafe_topics = [
        ("Fatal plane crash in the Alps leaves 12 dead", "casualties_accidents"),
        ("Active shooter reported at downtown mall", "violence_and_crimes"),
        ("New viral outbreak reported by health authorities", "health_and_disease"),
        ("Military airstrike kills civilians in conflict zone", "casualties_accidents"),
        ("Massive train derailment causes multiple fatalities", "casualties_accidents"),
        ("Suspect arrested in international trafficking probe", "violence_and_crimes"),
    ]
    for topic, expected_category in unsafe_topics:
        is_safe, category, matched = check_safety(topic)
        assert is_safe is False, f"Expected unsafe topic '{topic}' to fail, but passed"
        assert matched is not None


def test_evaluate_trend_safety_with_summary():
    # Safe title but tragic summary
    unsafe_trend = RawTrend(
        source="test",
        title="Breaking News in Metropolis",
        summary="A major explosion killed three workers at the chemical plant.",
        raw_score=100.0,
        published_at=datetime.now(timezone.utc),
    )
    is_safe, reason = evaluate_trend_safety(unsafe_trend)
    assert is_safe is False
    assert "Summary matched" in reason

    # Wholly safe trend
    safe_trend = RawTrend(
        source="test",
        title="Google drops new Pixel device",
        summary="Features faster chip and upgraded display.",
        raw_score=100.0,
        published_at=datetime.now(timezone.utc),
    )
    is_safe, reason = evaluate_trend_safety(safe_trend)
    assert is_safe is True
    assert reason is None
