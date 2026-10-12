"""SQLite-backed deduplication engine for recency window gating.

Maintains state of previously discovered trends to avoid surfacing or alerting
on the same news or discussion topic multiple times within a rolling window (e.g. 48 hours).
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from trend_copilot.config import settings
from trend_copilot.storage.db import get_connection, init_db
from .models import RawTrend, slugify_title


class Deduplicator:
    """Detects repeated trends across ingestion cycles using SQLite storage."""

    def __init__(
        self,
        db_path: Optional[Path | str] = None,
        window_hours: Optional[int] = None,
    ) -> None:
        self.db_path = db_path or settings.DB_PATH
        self.window_hours = window_hours or settings.DEDUP_WINDOW_HOURS
        # Ensure schema exists
        init_db(self.db_path)

    def is_duplicate(self, trend: RawTrend) -> bool:
        """Check if trend slug or hash was seen within the recency window.

        Args:
            trend: Candidate RawTrend.

        Returns:
            True if seen within window_hours, False otherwise.
        """
        slug = trend.slug or slugify_title(trend.title)
        window_modifier = f"-{self.window_hours} hours"

        query = """
        SELECT id FROM trends
        WHERE (slug = ? OR trend_hash = ?)
          AND first_seen_at > datetime('now', ?)
        LIMIT 1;
        """

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (slug, trend.id, window_modifier))
            row = cursor.fetchone()
            if row:
                # Update last_seen_at timestamp
                update_query = """
                UPDATE trends
                SET last_seen_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """
                conn.execute(update_query, (row["id"],))
                return True

        return False

    def record_trend(
        self,
        trend: RawTrend,
        status: str = "pending",
        rejection_reason: Optional[str] = None,
        velocity_score: float = 0.0,
    ) -> int:
        """Insert or update a trend record in SQLite.

        Args:
            trend: Candidate RawTrend.
            status: Lifecycle status ('qualified', 'dropped_safety', 'dropped_duplicate', etc.).
            rejection_reason: Explanation if dropped.
            velocity_score: Computed velocity score.

        Returns:
            The SQLite row id of the inserted/updated record.
        """
        slug = trend.slug or slugify_title(trend.title)

        upsert_sql = """
        INSERT INTO trends (
            trend_hash, slug, source, title, summary, url,
            raw_score, comment_count, velocity_score, status, rejection_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(trend_hash) DO UPDATE SET
            last_seen_at = CURRENT_TIMESTAMP,
            raw_score = excluded.raw_score,
            comment_count = excluded.comment_count,
            velocity_score = excluded.velocity_score,
            status = excluded.status,
            rejection_reason = excluded.rejection_reason
        RETURNING id;
        """

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                upsert_sql,
                (
                    trend.id,
                    slug,
                    trend.source,
                    trend.title,
                    trend.summary,
                    trend.url,
                    trend.raw_score,
                    trend.comment_count,
                    velocity_score,
                    status,
                    rejection_reason,
                ),
            )
            row = cursor.fetchone()
            return int(row["id"]) if row else -1

    def get_recent_slugs(self, hours: Optional[int] = None) -> List[str]:
        """Fetch all slugs seen within the specified recency window."""
        window = hours or self.window_hours
        window_modifier = f"-{window} hours"

        query = """
        SELECT DISTINCT slug FROM trends
        WHERE first_seen_at > datetime('now', ?);
        """

        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (window_modifier,))
            rows = cursor.fetchall()
            return [row["slug"] for row in rows]
