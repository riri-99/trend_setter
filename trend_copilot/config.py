"""Central application configuration for Trend Copilot.

Loads settings from environment variables and .env file with validated defaults.
"""

from pathlib import Path
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for Trend Copilot."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Base Paths
    BASE_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    DATA_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data")
    DB_PATH: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data" / "agent.db")

    # Ingestion & Filtering Settings
    MIN_VELOCITY_SCORE: float = Field(
        default=60.0,
        description="Minimum normalized velocity score (0-100) required to qualify a trend."
    )
    DEDUP_WINDOW_HOURS: int = Field(
        default=48,
        description="Time window in hours to prevent surfacing the same trend twice."
    )
    TOP_TRENDS_LIMIT: int = Field(
        default=5,
        description="Maximum number of top qualified trends output per cycle."
    )
    SIMILARITY_THRESHOLD: float = Field(
        default=75.0,
        description="Fuzzy string similarity threshold (0-100) to merge overlapping trends."
    )

    # Google Trends Collector Settings
    GOOGLE_TRENDS_GEO: str = Field(
        default="US",
        description="Default geographical region code for Google Trends RSS."
    )
    GOOGLE_TRENDS_RSS_URL: str = Field(
        default="https://trends.google.com/trending/rss?geo={geo}",
        description="Template URL for Google Trends RSS feed."
    )

    # Reddit Collector Settings
    REDDIT_CLIENT_ID: str = Field(default="", description="Reddit API client ID.")
    REDDIT_CLIENT_SECRET: str = Field(default="", description="Reddit API client secret.")
    REDDIT_USER_AGENT: str = Field(
        default="trend_copilot:v0.1.0 (by /u/trend_copilot_bot)",
        description="User-Agent string for Reddit requests."
    )
    REDDIT_SUBREDDITS: List[str] = Field(
        default=["all", "technology", "popculturechat", "entertainment", "antiwork"],
        description="Target subreddits monitored for viral discussions."
    )
    REDDIT_POST_LIMIT: int = Field(
        default=25,
        description="Max hot posts to pull per subreddit."
    )

    # Hacker News Collector Settings
    HACKERNEWS_TOP_STORIES_LIMIT: int = Field(
        default=30,
        description="Number of top stories to inspect from Hacker News."
    )
    HACKERNEWS_MIN_SCORE: int = Field(
        default=100,
        description="Minimum upvote score for Hacker News items."
    )
    HACKERNEWS_MAX_AGE_HOURS: float = Field(
        default=4.0,
        description="Maximum age in hours for Hacker News stories."
    )


# Singleton settings instance
settings = Settings()

# Ensure data directory exists
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
