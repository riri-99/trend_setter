"""Abstract base class and contract for all trend data collectors."""

import logging
from abc import ABC, abstractmethod
from typing import List
from ..models import RawTrend

logger = logging.getLogger("trend_copilot.collectors")


class BaseCollector(ABC):
    """Abstract interface that each platform-specific trend collector must implement."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique provider identifier (e.g. 'google_trends', 'reddit', 'hackernews')."""
        pass

    @abstractmethod
    async def fetch_trends(self) -> List[RawTrend]:
        """Fetch raw items and return normalized RawTrend models.

        Must be exception-resilient: log any operational errors and return an
        empty list rather than crashing the overarching ingestion pipeline.
        """
        pass
