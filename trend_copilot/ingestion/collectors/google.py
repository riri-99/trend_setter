"""Google Trends RSS feed collector.

Pulls real-time search trends directly from Google's official XML feed
without requiring API keys or encountering pytrends captcha blocks.
"""

import email.utils
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Optional
import httpx
from trend_copilot.config import settings
from ..models import RawTrend
from .base import BaseCollector

logger = logging.getLogger("trend_copilot.collectors.google")

HT_NS = {"ht": "https://trends.google.com/trending/rss"}


def parse_traffic_volume(traffic_str: Optional[str]) -> float:
    """Convert Google approximate traffic string (e.g. '200,000+', '50K+') to numeric float."""
    if not traffic_str:
        return 0.0

    cleaned = traffic_str.strip().upper().replace(",", "").replace("+", "")
    multiplier = 1.0

    if cleaned.endswith("K"):
        multiplier = 1_000.0
        cleaned = cleaned[:-1]
    elif cleaned.endswith("M"):
        multiplier = 1_000_000.0
        cleaned = cleaned[:-1]

    try:
        return float(cleaned) * multiplier
    except ValueError:
        return 0.0


def parse_pub_date(pub_date_str: Optional[str]) -> datetime:
    """Parse standard RFC 2822 pubDate string into timezone-aware UTC datetime."""
    if not pub_date_str:
        return datetime.now(timezone.utc)
    try:
        parsed_tuple = email.utils.parsedate_to_datetime(pub_date_str)
        if parsed_tuple.tzinfo is None:
            return parsed_tuple.replace(tzinfo=timezone.utc)
        return parsed_tuple.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


class GoogleTrendsCollector(BaseCollector):
    """Fetches trending search queries from Google Trends RSS."""

    def __init__(
        self,
        geo: Optional[str] = None,
        user_agent: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.geo = geo or settings.GOOGLE_TRENDS_GEO
        self.user_agent = user_agent or settings.GOOGLE_TRENDS_USER_AGENT
        self.timeout = timeout if timeout is not None else settings.REQUEST_TIMEOUT_SECONDS

    @property
    def source_name(self) -> str:
        return "google_trends"

    async def fetch_trends(self) -> List[RawTrend]:
        """Fetch and parse Google Trends RSS items into normalized RawTrend models."""
        url = settings.GOOGLE_TRENDS_RSS_URL.format(geo=self.geo)
        trends: List[RawTrend] = []

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/rss+xml, application/xml, text/xml",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                xml_content = response.text

            root = ET.fromstring(xml_content)
            items = root.findall(".//item")

            for item in items:
                title = (item.findtext("title") or "").strip()
                if not title:
                    continue

                raw_traffic = item.findtext("ht:approx_traffic", "", HT_NS)
                traffic_score = parse_traffic_volume(raw_traffic)

                pub_date_str = item.findtext("pubDate")
                published_at = parse_pub_date(pub_date_str)

                # Extract first news article snippet if available
                news_item = item.find("ht:news_item", HT_NS)
                summary: Optional[str] = None
                article_url: Optional[str] = None

                if news_item is not None:
                    news_title = news_item.findtext("ht:news_item_title", "", HT_NS).strip()
                    news_snippet = news_item.findtext("ht:news_item_snippet", "", HT_NS).strip()
                    # Clean any lingering HTML entities/tags in snippet
                    news_snippet = re.sub(r"<[^>]+>", "", news_snippet)
                    article_url = news_item.findtext("ht:news_item_url", "", HT_NS).strip() or None

                    if news_title and news_snippet:
                        summary = f"{news_title}: {news_snippet}"
                    elif news_snippet:
                        summary = news_snippet
                    elif news_title:
                        summary = news_title

                # Fallback to general item link and description
                if not article_url:
                    article_url = item.findtext("link")
                if not summary:
                    raw_desc = item.findtext("description") or ""
                    cleaned_desc = re.sub(r"<[^>]+>", "", raw_desc).strip()
                    summary = cleaned_desc if cleaned_desc else None

                trend = RawTrend(
                    source=self.source_name,
                    title=title,
                    summary=summary,
                    url=article_url,
                    raw_score=traffic_score,
                    comment_count=0,
                    published_at=published_at,
                    category_hint="general",
                )
                trends.append(trend)

            logger.info("Successfully fetched %d trends from Google Trends (%s)", len(trends), self.geo)

        except Exception as exc:
            logger.error("Error fetching Google Trends RSS: %s", exc, exc_info=True)

        return trends
