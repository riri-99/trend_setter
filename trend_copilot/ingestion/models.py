"""Data models for trend collection, scoring, and lifecycle tracking.

Defines Pydantic schemas for raw trends ingested from disparate sources,
scored trends after passing algorithmic filtering, and batch ingestion results.
"""

import hashlib
import re
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


def slugify_title(title: str) -> str:
    """Normalize a trend title into a clean slug for deduplication and hashing."""
    cleaned = title.lower().strip()
    # Replace non-alphanumeric characters with hyphens
    cleaned = re.sub(r"[^\w\s-]", "", cleaned)
    # Collapse whitespace and hyphens
    cleaned = re.sub(r"[-\s]+", "-", cleaned)
    return cleaned.strip("-") or "untitled"


def compute_trend_hash(source: str, title: str) -> str:
    """Deterministic MD5 hash for a given source and title slug."""
    slug = slugify_title(title)
    seed = f"{source}:{slug}".encode("utf-8")
    return hashlib.md5(seed).hexdigest()


def ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class RawTrend(BaseModel):
    """Normalized schema for raw trends ingested across any provider."""

    id: str = Field(
        default="",
        description="Computed deterministic hash: md5(source + slug(title))."
    )
    source: str = Field(
        ...,
        description="Source identifier (e.g., 'google_trends', 'reddit', 'hackernews')."
    )
    title: str = Field(
        ...,
        description="Cleaned trend headline or keyword query."
    )
    summary: Optional[str] = Field(
        default=None,
        description="News article summary, body snippet, or Reddit selftext."
    )
    url: Optional[str] = Field(
        default=None,
        description="Direct external link to the news item or discussion post."
    )
    raw_score: float = Field(
        default=0.0,
        description="Source-native metric (e.g. search volume, Reddit score, HN points)."
    )
    comment_count: int = Field(
        default=0,
        description="Total comments or discussion replies."
    )
    published_at: datetime = Field(
        ...,
        description="Publication or submission timestamp."
    )
    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when ingested by Trend Copilot."
    )
    category_hint: str = Field(
        default="general",
        description="Category classification hint ('tech', 'corporate', 'entertainment', 'general')."
    )
    slug: str = Field(
        default="",
        description="Computed slug of the title."
    )

    @model_validator(mode="after")
    def populate_computed_fields(self) -> "RawTrend":
        """Compute slug, id, and enforce UTC timezones."""
        if not self.slug:
            self.slug = slugify_title(self.title)
        if not self.id:
            self.id = compute_trend_hash(self.source, self.title)
        self.published_at = ensure_utc(self.published_at)
        self.fetched_at = ensure_utc(self.fetched_at)
        return self

    @property
    def age_in_hours(self) -> float:
        """Calculate age of the trend in hours relative to current UTC time."""
        now = datetime.now(timezone.utc)
        pub = ensure_utc(self.published_at)
        delta_seconds = max(0.0, (now - pub).total_seconds())
        return delta_seconds / 3600.0

    @property
    def controversy_ratio(self) -> float:
        """Ratio of comments to raw score. High ratio signals active debates/arguments."""
        return float(self.comment_count) / (float(self.raw_score) + 1.0)


class ScoredTrend(RawTrend):
    """Enriched trend candidate that has passed through safety and scoring gates."""

    velocity_score: float = Field(
        default=0.0,
        description="Normalized velocity index between 0.0 and 100.0."
    )
    is_breaking: bool = Field(
        default=False,
        description="Flag indicating surging velocity within <2 hours."
    )
    status: str = Field(
        default="pending",
        description="Status flag: 'qualified', 'dropped_safety', 'dropped_duplicate', 'dropped_low_velocity'."
    )
    rejection_reason: Optional[str] = Field(
        default=None,
        description="Details if discarded by safety blacklist or low threshold."
    )
    cross_source_mentions: List[str] = Field(
        default_factory=list,
        description="List of other collector sources where this trend was also detected."
    )


class IngestionResult(BaseModel):
    """Batch summary of an ingestion pipeline run."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_fetched: int = 0
    dropped_safety: int = 0
    dropped_duplicates: int = 0
    dropped_low_velocity: int = 0
    qualified_trends: List[ScoredTrend] = Field(default_factory=list)

    @property
    def qualified_count(self) -> int:
        return len(self.qualified_trends)
