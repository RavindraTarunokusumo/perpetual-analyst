"""Observation compaction: expire stale observations by importance/age. See SPEC §8."""

from __future__ import annotations

import sqlite3


def expire_observations(conn: sqlite3.Connection, topic_id: int | None = None) -> int:
    """Mark active observations as expired based on importance and age thresholds.

    Rules:
    - importance 1: expires after 30 days
    - importance 2: expires after 90 days
    - importance 3: never expires
    - Only 'active' observations are candidates; 'promoted' and already 'expired' are untouched.

    Args:
        conn: SQLite connection with row_factory set (see db.py).
        topic_id: If provided, restrict expiry to this topic only.

    Returns:
        Number of rows changed.
    """
    topic_filter = "AND topic_id = :topic_id" if topic_id is not None else ""
    sql = f"""
        UPDATE observations
        SET status = 'expired'
        WHERE status = 'active'
          AND (
              (importance = 1 AND created_at < datetime('now', '-30 days'))
              OR
              (importance = 2 AND created_at < datetime('now', '-90 days'))
          )
          {topic_filter}
    """
    with conn:
        cur = conn.execute(sql, {"topic_id": topic_id} if topic_id is not None else {})
    return cur.rowcount
