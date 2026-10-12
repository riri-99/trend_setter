"""Unit tests for individual source collectors with mocks."""

from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from trend_copilot.ingestion.collectors.base import BaseCollector
from trend_copilot.ingestion.collectors.google import (
    GoogleTrendsCollector,
    parse_traffic_volume,
)
from trend_copilot.ingestion.collectors.hackernews import HackerNewsCollector
from trend_copilot.ingestion.collectors.reddit import RedditCollector


def test_parse_traffic_volume():
    assert parse_traffic_volume("200,000+") == 200000.0
    assert parse_traffic_volume("50K+") == 50000.0
    assert parse_traffic_volume("1M+") == 1000000.0
    assert parse_traffic_volume("500+") == 500.0
    assert parse_traffic_volume(None) == 0.0
    assert parse_traffic_volume("invalid") == 0.0


@pytest.mark.asyncio
async def test_google_trends_collector_parsing():
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
        <channel>
            <item>
                <title>OpenAI Strawberry</title>
                <ht:approx_traffic>200,000+</ht:approx_traffic>
                <pubDate>Wed, 07 Oct 2026 12:00:00 GMT</pubDate>
                <ht:news_item>
                    <ht:news_item_title>OpenAI Releases Strawberry</ht:news_item_title>
                    <ht:news_item_snippet>The model demonstrates enhanced reasoning capability.</ht:news_item_snippet>
                    <ht:news_item_url>https://techcrunch.com/strawberry</ht:news_item_url>
                </ht:news_item>
            </item>
        </channel>
    </rss>
    """

    collector = GoogleTrendsCollector(geo="US")

    mock_resp = MagicMock()
    mock_resp.text = sample_xml
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        trends = await collector.fetch_trends()

    assert len(trends) == 1
    t = trends[0]
    assert t.title == "OpenAI Strawberry"
    assert t.raw_score == 200000.0
    assert t.url == "https://techcrunch.com/strawberry"
    assert "OpenAI Releases Strawberry" in t.summary


@pytest.mark.asyncio
async def test_hackernews_collector_filtering():
    collector = HackerNewsCollector(min_score=100, max_age_hours=4.0)

    now_ts = int(datetime.now(timezone.utc).timestamp())
    mock_item_qualified = {
        "id": 1,
        "type": "story",
        "title": "Postgres 18 Released",
        "score": 150,
        "descendants": 50,
        "time": now_ts - 3600,  # 1 hour ago
        "url": "https://postgresql.org/18",
    }
    mock_item_low_score = {
        "id": 2,
        "type": "story",
        "title": "Random Blog Post",
        "score": 10,
        "descendants": 2,
        "time": now_ts - 1800,
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        # First call: topstories.json, Subsequent: items
        mock_resp_ids = MagicMock()
        mock_resp_ids.json.return_value = [1, 2]
        mock_resp_ids.raise_for_status = MagicMock()

        async def fake_get(url, **kwargs):
            if "topstories" in str(url):
                return mock_resp_ids
            elif "item/1" in str(url):
                resp = MagicMock()
                resp.status_code = 200
                resp.json.return_value = mock_item_qualified
                return resp
            else:
                resp = MagicMock()
                resp.status_code = 200
                resp.json.return_value = mock_item_low_score
                return resp

        mock_get.side_effect = fake_get
        trends = await collector.fetch_trends()

    # Only item 1 meets min_score=100
    assert len(trends) == 1
    assert trends[0].title == "Postgres 18 Released"
    assert trends[0].raw_score == 150.0


@pytest.mark.asyncio
async def test_reddit_collector_without_credentials_skips_cleanly():
    collector = RedditCollector(client_id="", client_secret="")
    trends = await collector.fetch_trends()
    assert trends == []


def test_collector_custom_configurations():
    google = GoogleTrendsCollector(geo="UK", user_agent="CustomAgent/1.0", timeout=25.0)
    assert google.geo == "UK"
    assert google.user_agent == "CustomAgent/1.0"
    assert google.timeout == 25.0

    hn = HackerNewsCollector(top_limit=50, min_score=200, max_age_hours=6.0, concurrency=20, timeout=30.0)
    assert hn.top_limit == 50
    assert hn.min_score == 200
    assert hn.max_age_hours == 6.0
    assert hn.concurrency == 20
    assert hn.timeout == 30.0

    custom_cats = {"localllama": "ai"}
    reddit = RedditCollector(category_map=custom_cats, post_limit=10)
    assert reddit.category_map == custom_cats
    assert reddit.post_limit == 10

