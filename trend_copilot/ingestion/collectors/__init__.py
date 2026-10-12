"""Data collectors package for Trend Copilot."""

from .base import BaseCollector
from .google import GoogleTrendsCollector
from .hackernews import HackerNewsCollector
from .reddit import RedditCollector

__all__ = [
    "BaseCollector",
    "GoogleTrendsCollector",
    "HackerNewsCollector",
    "RedditCollector",
]
