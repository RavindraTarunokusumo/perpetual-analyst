"""Thesis lifecycle helpers: stale-flagging and report rendering. See SPEC §8.

Thesis CRUD (apply_thesis_update, get_active_theses) lives in analyst/memory.py,
the transactional write path owned by apply_all_memory_writes.
"""

from __future__ import annotations

import sqlite3

from perpetual_analyst.store.models import Thesis


def get_stale_theses(topic_id: int, conn: sqlite3.Connection, days: int = 30) -> list[Thesis]:
    """Active theses untouched (no update; fallback: creation) for more than `days` days."""
    rows = conn.execute(
        """SELECT * FROM theses
           WHERE topic_id = ? AND status = 'active'
             AND datetime(COALESCE(updated_at, created_at)) <= datetime('now', ?)""",
        (topic_id, f"-{days} days"),
    ).fetchall()
    return [Thesis.from_row(row) for row in rows]
