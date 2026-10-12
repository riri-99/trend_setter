"""SQLite storage layer for trends and bot interactions.

Manages the schema initialization, connection lifecycle, and WAL journaling
to prevent locking during concurrent reads and writes.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional
from trend_copilot.config import settings


CREATE_TABLES_SQL = """
-- Trends table: records ingested trends, lifecycle status, and scoring metrics
CREATE TABLE IF NOT EXISTS trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trend_hash TEXT UNIQUE NOT NULL,
    slug TEXT NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    url TEXT,
    raw_score REAL DEFAULT 0.0,
    comment_count INTEGER DEFAULT 0,
    velocity_score REAL DEFAULT 0.0,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'pending',
    rejection_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_trends_hash ON trends(trend_hash);
CREATE INDEX IF NOT EXISTS idx_trends_slug ON trends(slug);
CREATE INDEX IF NOT EXISTS idx_trends_first_seen ON trends(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_trends_status ON trends(status);

-- Generated drafts table: records LLM draft generation, Discord IDs, and user selections
CREATE TABLE IF NOT EXISTS generated_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trend_id INTEGER REFERENCES trends(id) ON DELETE CASCADE,
    discord_message_id TEXT,
    discord_thread_id TEXT,
    irony_summary TEXT,
    draft_x TEXT,
    draft_linkedin TEXT,
    draft_cynical TEXT,
    selected_option TEXT,
    final_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_drafts_trend_id ON generated_drafts(trend_id);
"""


def get_db_path(db_path: Optional[Path | str] = None) -> Path:
    """Resolve database path, defaulting to configured settings path."""
    if db_path is None:
        target = settings.DB_PATH
    else:
        target = Path(db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


@contextmanager
def get_connection(db_path: Optional[Path | str] = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager yielding a SQLite connection with WAL mode and foreign keys enabled."""
    path = get_db_path(db_path)
    conn = sqlite3.connect(path, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[Path | str] = None) -> None:
    """Initialize database tables and indexes."""
    with get_connection(db_path) as conn:
        conn.executescript(CREATE_TABLES_SQL)
