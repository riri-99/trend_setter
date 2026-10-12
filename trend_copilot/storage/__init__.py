"""Storage package for Trend Copilot state persistence."""

from .db import init_db, get_connection

__all__ = ["init_db", "get_connection"]
