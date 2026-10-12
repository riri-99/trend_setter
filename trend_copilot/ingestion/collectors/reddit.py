"""Reddit hot post scanner utilizing PRAW (Python Reddit API Wrapper).

Pulls fast-rising discussions from viral and tech subreddits (r/all, r/technology,
r/popculturechat, r/antiwork), tracking upvote velocity and controversy ratios.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
import praw
from praw.exceptions import PRAWException
from trend_copilot.config import settings
from ..models import RawTrend
from .base import BaseCollector

logger = logging.getLogger("trend_copilot.collectors.reddit")

SUBREDDIT_CATEGORY_MAP: Dict[str, str] = {
    "technology": "tech",
    "popculturechat": "entertainment",
    "entertainment": "entertainment",
    "antiwork": "corporate",
    "recruitinghell": "corporate",
    "all": "general",
}


class RedditCollector(BaseCollector):
    """Monitors viral discussions across target subreddits using PRAW."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        user_agent: Optional[str] = None,
        subreddits: Optional[List[str]] = None,
        post_limit: Optional[int] = None,
        category_map: Optional[Dict[str, str]] = None,
    ) -> None:
        self.client_id = client_id or settings.REDDIT_CLIENT_ID
        self.client_secret = client_secret or settings.REDDIT_CLIENT_SECRET
        self.user_agent = user_agent or settings.REDDIT_USER_AGENT
        self.subreddits = subreddits or settings.REDDIT_SUBREDDITS
        self.post_limit = post_limit or settings.REDDIT_POST_LIMIT
        self.category_map = category_map or SUBREDDIT_CATEGORY_MAP

    @property
    def source_name(self) -> str:
        return "reddit"

    def _has_credentials(self) -> bool:
        """Verify if Reddit OAuth credentials are provided."""
        return bool(self.client_id and self.client_secret)

    def _fetch_subreddit_posts(self, reddit: praw.Reddit, sub_name: str) -> List[RawTrend]:
        """Synchronous fetch executed inside an asyncio worker thread."""
        trends: List[RawTrend] = []
        category = self.category_map.get(sub_name.lower(), "general")

        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.hot(limit=self.post_limit):
                # Skip pinned/stickied announcements
                if getattr(post, "stickied", False):
                    continue

                title = (post.title or "").strip()
                if not title:
                    continue

                # Prepare summary snippet from selftext if available
                selftext = (post.selftext or "").strip()
                summary = selftext[:300] + ("..." if len(selftext) > 300 else "") if selftext else None

                pub_time = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
                permalink = f"https://www.reddit.com{post.permalink}" if hasattr(post, "permalink") else None

                trend = RawTrend(
                    source=self.source_name,
                    title=title,
                    summary=summary,
                    url=permalink,
                    raw_score=float(post.score),
                    comment_count=int(post.num_comments),
                    published_at=pub_time,
                    category_hint=category,
                )
                trends.append(trend)

        except Exception as exc:
            logger.warning("Error fetching subreddit r/%s: %s", sub_name, exc)

        return trends

    async def fetch_trends(self) -> List[RawTrend]:
        """Fetch hot posts across all designated subreddits concurrently."""
        if not self._has_credentials():
            logger.info("Reddit credentials (REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET) not set. Skipping Reddit collection.")
            return []

        trends: List[RawTrend] = []

        try:
            reddit = praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent,
                read_only=True,
            )

            # Run synchronous PRAW calls concurrently across threadpool
            tasks = [
                asyncio.to_thread(self._fetch_subreddit_posts, reddit, sub)
                for sub in self.subreddits
            ]
            results = await asyncio.gather(*tasks)

            for sub_trends in results:
                trends.extend(sub_trends)

            logger.info("Successfully fetched %d posts across %d subreddits from Reddit", len(trends), len(self.subreddits))

        except PRAWException as praw_err:
            logger.error("PRAW operational failure: %s", praw_err, exc_info=True)
        except Exception as exc:
            logger.error("Unexpected error in RedditCollector: %s", exc, exc_info=True)

        return trends
