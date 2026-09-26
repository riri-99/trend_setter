# Trend Copilot (AI Trend-Jacking Discord Agent)

An autonomous trend-detection and content-synthesis agent operating with a Human-in-the-Loop (HITL) Discord interface. It captures fast-rising cultural and tech trends across Reddit, Google Trends, and news sources, extracts the core conflict/irony, drafts multi-platform satirical takes, and presents an interactive Discord card for 1-tap sharing and thread-based iteration.

---

## Documentation

* **[ARCHITECTURE.md](ARCHITECTURE.md)**: Full technical architecture, system topology, database schema, Discord component specs, and step-by-step build roadmap.
* **[COMPONENT_1_PLAN.md](COMPONENT_1_PLAN.md)**: Granular implementation plan for the Trend Ingestion & Filtering Engine (data collectors, controversy scoring, safety blacklist, and deduplication).

---

## Core Capabilities

1. **Trend Discovery Engine**: Google Trends RSS, Reddit hot threads (`r/all`, `r/technology`), and velocity filtering.
2. **Safety & Tragedy Blacklist**: Automatic keyword and semantic guardrails to prevent satirical commentary on sensitive or tragic world events.
3. **Context & Irony Engine (LLM)**: Analyzes the conflict (Camp A vs. Camp B) and drafts 3 tailored takes:
   * **X (Twitter)**: Short, snappy one-liners.
   * **LinkedIn**: Corporate satire and hustle culture parody.
   * **Hot Take**: Thought-provoking cultural cynicism.
4. **Discord Cockpit**:
   * Rich Embeds with trend velocity tags.
   * 1-Tap X compose via URL Web Intent (`https://twitter.com/intent/tweet?text=...`).
   * Discord Modals for editing text directly inside Discord.
   * Auto-created Discord Threads for live conversational refinement with the LLM.
