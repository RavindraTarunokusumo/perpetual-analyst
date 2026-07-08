"""Thesis lifecycle: stale-flagging and rendering. See SPEC §8."""

from __future__ import annotations

import sqlite3
from collections import defaultdict

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


def render_thesis_trail(topic_id: int, conn: sqlite3.Connection) -> str:
    """Return a one-line confidence trajectory for each active thesis that has updates.

    Format: - [thesis:{id}] confidence {start:.2f}→{end:.2f} over {n} update(s)
    Order by thesis id. Returns '(no thesis history)' if no active thesis has any updates.
    """
    rows = conn.execute(
        """SELECT t.id AS thesis_id,
                  tu.confidence_before,
                  tu.confidence_after,
                  tu.created_at
           FROM theses t
           JOIN thesis_updates tu ON tu.thesis_id = t.id
           WHERE t.topic_id = ? AND t.status = 'active'
           ORDER BY t.id, tu.created_at""",
        (topic_id,),
    ).fetchall()

    # Group updates by thesis_id preserving insertion order
    by_thesis: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        by_thesis[row["thesis_id"]].append(
            {
                "confidence_before": row["confidence_before"],
                "confidence_after": row["confidence_after"],
            }
        )

    if not by_thesis:
        return "(no thesis history)"

    lines: list[str] = []
    for thesis_id in sorted(by_thesis):
        updates = by_thesis[thesis_id]
        # Start: earliest non-null confidence_before, falling back to earliest confidence_after
        start: float | None = None
        for u in updates:
            if u["confidence_before"] is not None:
                start = u["confidence_before"]
                break
        if start is None:
            for u in updates:
                if u["confidence_after"] is not None:
                    start = u["confidence_after"]
                    break
        # End: latest confidence_after
        end: float | None = None
        for u in reversed(updates):
            if u["confidence_after"] is not None:
                end = u["confidence_after"]
                break
        if start is None or end is None:
            continue
        lines.append(
            f"- [thesis:{thesis_id}] confidence {start:.2f}→{end:.2f} over {len(updates)} update(s)"
        )

    return "\n".join(lines) if lines else "(no thesis history)"
