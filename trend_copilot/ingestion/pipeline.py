"""Pipeline coordinator for Component 1: Trend Detection & Ingestion Engine.

Coordinates the end-to-end data flow:
1. Concurrently queries all source collectors (Google Trends RSS, Reddit, Hacker News).
2. Executes Tier 1 Safety & Tragedy Blacklist filtering (zero token cost).
3. Executes Tier 2 SQLite Deduplication filtering (48h rolling window).
4. Executes Tier 3 Velocity & Controversy scoring.
5. Fuses cross-source matching stories with RapidFuzz.
6. Persists candidates and returns top qualified trends for the LLM drafting layer.
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import List, Optional
from trend_copilot.config import settings
from .blacklist import evaluate_trend_safety
from .collectors import (
    BaseCollector,
    GoogleTrendsCollector,
    HackerNewsCollector,
    RedditCollector,
)
from .deduplicator import Deduplicator
from .models import IngestionResult, RawTrend, ScoredTrend
from .scorer import merge_cross_source_trends, score_candidate

logger = logging.getLogger("trend_copilot.pipeline")


class IngestionPipeline:
    """Orchestrates multi-source collection, 3-tier filtering, and trend ranking."""

    def __init__(
        self,
        collectors: Optional[List[BaseCollector]] = None,
        deduplicator: Optional[Deduplicator] = None,
        min_velocity: Optional[float] = None,
        top_limit: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
        cross_source_boost: Optional[float] = None,
    ) -> None:
        self.collectors = collectors if collectors is not None else [
            GoogleTrendsCollector(),
            HackerNewsCollector(),
            RedditCollector(),
        ]
        self.deduplicator = deduplicator or Deduplicator()
        self.min_velocity = min_velocity if min_velocity is not None else settings.MIN_VELOCITY_SCORE
        self.top_limit = top_limit or settings.TOP_TRENDS_LIMIT
        self.similarity_threshold = (
            similarity_threshold if similarity_threshold is not None else settings.SIMILARITY_THRESHOLD
        )
        self.cross_source_boost = (
            cross_source_boost if cross_source_boost is not None else settings.CROSS_SOURCE_BOOST
        )

    async def run(self) -> IngestionResult:
        """Execute one complete ingestion and filtering cycle.

        Returns:
            IngestionResult containing processing statistics and top qualified trends.
        """
        result = IngestionResult()
        logger.info("Starting ingestion cycle across %d collectors...", len(self.collectors))

        # 1. Fetch raw items concurrently across all collectors
        collector_tasks = [collector.fetch_trends() for collector in self.collectors]
        raw_results = await asyncio.gather(*collector_tasks, return_exceptions=True)

        all_raw_trends: List[RawTrend] = []
        for i, res in enumerate(raw_results):
            collector_name = self.collectors[i].source_name
            if isinstance(res, Exception):
                logger.error("Collector '%s' raised an unhandled exception: %s", collector_name, res)
            elif isinstance(res, list):
                all_raw_trends.extend(res)

        result.total_fetched = len(all_raw_trends)
        logger.info("Total raw items gathered: %d", result.total_fetched)

        # 2. Tier 1: Safety & Tragedy Blacklist Filtering
        safe_candidates: List[RawTrend] = []
        for raw in all_raw_trends:
            is_safe, safety_reason = evaluate_trend_safety(raw)
            if not is_safe:
                result.dropped_safety += 1
                self.deduplicator.record_trend(
                    raw,
                    status="dropped_safety",
                    rejection_reason=safety_reason,
                    velocity_score=0.0,
                )
                logger.debug("Dropped by safety filter: '%s' (%s)", raw.title, safety_reason)
            else:
                safe_candidates.append(raw)

        # 3. Tier 2: SQLite Deduplication (Recency Window)
        novel_candidates: List[RawTrend] = []
        for candidate in safe_candidates:
            if self.deduplicator.is_duplicate(candidate):
                result.dropped_duplicates += 1
                logger.debug("Dropped as duplicate in recency window: '%s'", candidate.title)
            else:
                novel_candidates.append(candidate)

        # 4. Tier 3: Velocity & Score Normalization
        velocity_candidates: List[ScoredTrend] = []
        for candidate in novel_candidates:
            scored = score_candidate(candidate, min_threshold=self.min_velocity)
            if scored.status != "qualified":
                result.dropped_low_velocity += 1
                self.deduplicator.record_trend(
                    candidate,
                    status="dropped_low_velocity",
                    rejection_reason=scored.rejection_reason,
                    velocity_score=scored.velocity_score,
                )
            else:
                velocity_candidates.append(scored)

        # 5. Cross-Source Merging (RapidFuzz fusion)
        merged_candidates = merge_cross_source_trends(
            velocity_candidates,
            threshold=self.similarity_threshold,
            cross_source_boost=self.cross_source_boost,
        )

        # 6. Rank by Velocity Score and take Top N
        merged_candidates.sort(key=lambda t: t.velocity_score, reverse=True)
        top_candidates = merged_candidates[: self.top_limit]

        # 7. Record qualified winners into SQLite
        for winner in top_candidates:
            self.deduplicator.record_trend(
                winner,
                status="qualified",
                rejection_reason=None,
                velocity_score=winner.velocity_score,
            )

        result.qualified_trends = top_candidates
        logger.info(
            "Ingestion cycle completed. Qualified: %d, Safety dropped: %d, Dups dropped: %d, Low vel dropped: %d",
            len(result.qualified_trends),
            result.dropped_safety,
            result.dropped_duplicates,
            result.dropped_low_velocity,
        )

        return result


async def main() -> None:
    """CLI execution entrypoint for testing the ingestion engine."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Ensure safe console output across Windows code pages
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("\n" + "=" * 65)
    print(">>> TREND COPILOT -- COMPONENT 1 INGESTION ENGINE")
    print("=" * 65)

    pipeline = IngestionPipeline()
    result = await pipeline.run()

    print("\n" + "-" * 65)
    print("[*] INGESTION SUMMARY REPORT")
    print("-" * 65)
    print(f"  * Total Raw Items Fetched:      {result.total_fetched}")
    print(f"  * Dropped by Safety Blacklist:  {result.dropped_safety}")
    print(f"  * Dropped as Duplicates (48h):  {result.dropped_duplicates}")
    print(f"  * Dropped for Low Velocity:     {result.dropped_low_velocity}")
    print(f"  * High-Signal Trends Qualified: {result.qualified_count}")
    print("-" * 65)

    if result.qualified_trends:
        print("\n[+] TOP QUALIFIED TREND CANDIDATES (READY FOR LLM LAYER):")
        for idx, trend in enumerate(result.qualified_trends, 1):
            breaking_badge = " [BREAKING]" if trend.is_breaking else ""
            sources = ", ".join(trend.cross_source_mentions)
            print(f"\n{idx}. {trend.title}{breaking_badge}")
            print(f"     Velocity Index:     {trend.velocity_score:.1f}/100")
            print(f"     Sources:            {sources}")
            print(f"     Category:           {trend.category_hint}")
            print(f"     Controversy Ratio:  {trend.controversy_ratio:.2f}")
            if trend.url:
                print(f"     URL:                {trend.url}")
            if trend.summary:
                snippet = trend.summary[:120] + ("..." if len(trend.summary) > 120 else "")
                print(f"     Context Snippet:    {snippet}")
    else:
        print("\n[i] No candidates met the minimum velocity threshold in this cycle.")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
