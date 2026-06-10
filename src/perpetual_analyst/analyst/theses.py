"""Thesis lifecycle: stale-flagging and rendering. See SPEC §8."""

from __future__ import annotations

import sqlite3

from perpetual_analyst.store.models import Thesis


def get_stale_theses(topic_id: int, conn: sqlite3.Connection, days: int = 30) -> list[Thesis]:
    """Return active theses where coalesce(updated_at, created_at) is older than `days` days."""
    rows = conn.execute(
        f"""SELECT * FROM theses
            WHERE topic_id = ? AND status = 'active'
              AND coalesce(updated_at, created_at) < datetime('now', '-{days} days')""",
        (topic_id,),
    ).fetchall()
    return [Thesis.from_row(row) for row in rows]


def render_thesis_fragment(topic_id: int, conn: sqlite3.Connection) -> str:
    """Return markdown fragment listing active theses with confidence scores.

    Format each line: - [thesis:{id}] (conf {confidence:.0%}) {statement}
    Include "(stale)" marker for theses older than 30 days.
    Return '(no active theses)' if none.
    """
    rows = conn.execute(
        """SELECT *,
               coalesce(updated_at, created_at) < datetime('now', '-30 days') AS is_stale
           FROM theses WHERE topic_id = ? AND status = 'active'""",
        (topic_id,),
    ).fetchall()

    if not rows:
        return "(no active theses)"

    lines: list[str] = []
    for row in rows:
        is_stale = bool(row["is_stale"])
        thesis = Thesis(**{k: row[k] for k in row.keys() if k != "is_stale"})
        confidence_str = f"{thesis.confidence:.0%}" if thesis.confidence is not None else "N/A"
        stale_marker = " (stale)" if is_stale else ""
        lines.append(
            f"- [thesis:{thesis.id}] (conf {confidence_str}) {thesis.statement}{stale_marker}"
        )
    return "\n".join(lines)
