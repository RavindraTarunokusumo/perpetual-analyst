"""FTS5 keyword search helpers for the analyst's related-context retrieval. See SPEC §6."""

from __future__ import annotations

import logging
import re
import sqlite3

from perpetual_analyst.store.models import Item, Observation

logger = logging.getLogger(__name__)

_SPECIAL_CHARS = re.compile(r"[^\w\s]", re.UNICODE)


def _build_fts_query(text: str) -> str | None:
    """Extract first 100 chars from text, strip FTS special chars, return None if empty."""
    snippet = text[:100]
    cleaned = _SPECIAL_CHARS.sub(" ", snippet).strip()
    # Take the first meaningful word to avoid FTS parse errors
    words = cleaned.split()
    if not words:
        return None
    return " ".join(words)


def related_observations(
    text: str, topic_id: int, conn: sqlite3.Connection, k: int = 5
) -> list[Observation]:
    """FTS5 keyword search against observations_fts, filtered to topic and active status.

    Returns up to k Observation objects, recency-boosted (last 30 days first).
    Returns [] if text is empty or FTS query fails.
    """
    query = _build_fts_query(text)
    if not query:
        return []

    try:
        _recent_obs = "CASE WHEN obs.created_at > datetime('now', '-30 days') THEN 1 ELSE 0 END"
        rows = conn.execute(
            f"""SELECT obs.* FROM observations obs
               JOIN observations_fts fts ON fts.rowid = obs.id
               WHERE observations_fts MATCH ?
                 AND obs.topic_id = ? AND obs.status = 'active'
               ORDER BY ({_recent_obs}) DESC, rank
               LIMIT ?""",
            (query, topic_id, k),
        ).fetchall()
        return [Observation.from_row(row) for row in rows]
    except Exception:
        logger.warning("related_observations FTS query failed for query=%r", query, exc_info=True)
        return []


def related_items(text: str, topic_id: int, conn: sqlite3.Connection, k: int = 3) -> list[Item]:
    """FTS5 keyword search against items_fts, filtered to this topic's sources.

    Returns up to k Item objects, recency-boosted (last 14 days first).
    Returns [] if text is empty or FTS query fails.
    """
    query = _build_fts_query(text)
    if not query:
        return []

    try:
        _recent_items = "CASE WHEN i.fetched_at > datetime('now', '-14 days') THEN 1 ELSE 0 END"
        rows = conn.execute(
            f"""SELECT i.* FROM items i
               JOIN items_fts fts ON fts.rowid = i.id
               JOIN topic_sources ts ON ts.source_id = i.source_id
               WHERE items_fts MATCH ?
                 AND ts.topic_id = ?
               ORDER BY ({_recent_items}) DESC, rank
               LIMIT ?""",
            (query, topic_id, k),
        ).fetchall()
        return [Item.from_row(row) for row in rows]
    except Exception:
        logger.warning("related_items FTS query failed for query=%r", query, exc_info=True)
        return []
