"""Hacker News Firebase API collector.

Monitors fast-rising tech, startup, and AI developments by querying
Hacker News's official, open Firebase REST API.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from trend_copilot.config import settings
from ..models import RawTrend
from .base import BaseCollector

logger = logging.getLogger("trend_copilot.collectors.hackernews")

HN_TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"


class HackerNewsCollector(BaseCollector):
    """Fetches high-velocity tech stories from Hacker News."""

    def __init__(
        self,
        top_limit: Optional[int] = None,
        min_score: Optional[int] = None,
        max_age_hours: Optional[float] = None,
        concurrency: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.top_limit = top_limit or settings.HACKERNEWS_TOP_STORIES_LIMIT
        self.min_score = min_score if min_score is not None else settings.HACKERNEWS_MIN_SCORE
        self.max_age_hours = max_age_hours if max_age_hours is not None else settings.HACKERNEWS_MAX_AGE_HOURS
        self.concurrency = concurrency or settings.HACKERNEWS_CONCURRENCY
        self.timeout = timeout if timeout is not None else settings.REQUEST_TIMEOUT_SECONDS

    @property
    def source_name(self) -> str:
        return "hackernews"

    async def _fetch_item(self, client: httpx.AsyncClient, semaphore: asyncio.Semaphore, item_id: int) -> Optional[Dict[str, Any]]:
        """Fetch details for a single HN story."""
        url = HN_ITEM_URL.format(item_id=item_id)
        async with semaphore:
            try:
                res = await client.get(url, timeout=self.timeout)
                if res.status_code == 200:
                    return res.json()
            except Exception as err:
                logger.debug("Failed to fetch HN item %s: %s", item_id, err)
        return None

    async def fetch_trends(self) -> List[RawTrend]:
        """Fetch top story IDs, retrieve metadata concurrently, and filter high-velocity stories."""
        trends: List[RawTrend] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.get(HN_TOP_STORIES_URL)
                res.raise_for_status()
                top_ids: List[int] = res.json()[: self.top_limit]

                semaphore = asyncio.Semaphore(self.concurrency)
                tasks = [self._fetch_item(client, semaphore, item_id) for item_id in top_ids]
                items = await asyncio.gather(*tasks)

            now = datetime.now(timezone.utc)

            for item in items:
                if not item or item.get("type") != "story":
                    continue

                title = (item.get("title") or "").strip()
                if not title:
                    continue

                score = float(item.get("score") or 0)
                comment_count = int(item.get("descendants") or 0)
                item_time = item.get("time")

                if item_time:
                    published_at = datetime.fromtimestamp(item_time, tz=timezone.utc)
                else:
                    published_at = now

                age_hours = max(0.0, (now - published_at).total_seconds()) / 3600.0

                # Filter by score and age
                if score < self.min_score or age_hours > self.max_age_hours:
                    continue

                url = item.get("url") or f"https://news.ycombinator.com/item?id={item.get('id')}"
                author = item.get("by", "anonymous")
                summary = f"Hacker News discussion submitted by {author} with {comment_count} comments."

                trend = RawTrend(
                    source=self.source_name,
                    title=title,
                    summary=summary,
                    url=url,
                    raw_score=score,
                    comment_count=comment_count,
                    published_at=published_at,
                    category_hint="tech",
                )
                trends.append(trend)

            logger.info("Successfully fetched %d qualified stories from Hacker News", len(trends))

        except Exception as exc:
            logger.error("Error fetching Hacker News trends: %s", exc, exc_info=True)

        return trends
