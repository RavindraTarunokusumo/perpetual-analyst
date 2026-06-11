"""Per-source quality scoring: triage hit-rate + citation rate. See SPEC §11."""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

TRIAGE_HIT_THRESHOLD = 0.4


@dataclass
class SourceQuality:
    source_id: int
    name: str | None
    total_items: int
    hit_rate: float
    citation_rate: float
    score: float
    status: str


def compute_source_quality(conn: sqlite3.Connection) -> list[SourceQuality]:
    """Compute and persist quality_score for every source that has at least one item.

    For each source:
      hit_rate      = items with triage_score >= TRIAGE_HIT_THRESHOLD / total_items
      citation_rate = COUNT(DISTINCT cited item_id) / total_items  (capped at 1.0)
      score         = round(0.5 * hit_rate + 0.5 * citation_rate, 4)

    Writes quality_score back to sources in a single transaction.

    Returns a list of SourceQuality ordered by score descending.
    """
    rows = conn.execute(
        """
        SELECT
            s.id                                                          AS source_id,
            s.name,
            s.status,
            COUNT(i.id)                                                   AS total_items,
            SUM(CASE WHEN i.triage_score >= :threshold THEN 1 ELSE 0 END) AS hits,
            (SELECT COUNT(DISTINCT c.item_id)
               FROM citations c
              WHERE c.source_id = s.id)                                   AS cited
        FROM sources s
        JOIN items i ON i.source_id = s.id
        GROUP BY s.id
        """,
        {"threshold": TRIAGE_HIT_THRESHOLD},
    ).fetchall()

    results: list[SourceQuality] = []
    updates: list[tuple[float, int]] = []

    for row in rows:
        total = row["total_items"]
        if total == 0:
            continue

        hit_rate = row["hits"] / total
        citation_rate = min(row["cited"] / total, 1.0)
        score = round(0.5 * hit_rate + 0.5 * citation_rate, 4)

        results.append(
            SourceQuality(
                source_id=row["source_id"],
                name=row["name"],
                total_items=total,
                hit_rate=hit_rate,
                citation_rate=citation_rate,
                score=score,
                status=row["status"] or "active",
            )
        )
        updates.append((score, row["source_id"]))

    with conn:
        for score, source_id in updates:
            conn.execute(
                "UPDATE sources SET quality_score = ? WHERE id = ?",
                (score, source_id),
            )

    results.sort(key=lambda sq: sq.score, reverse=True)
    return results


def transition_probation(conn: sqlite3.Connection) -> int:
    """Promote probation sources whose probation_until has passed to status='active'.

    Returns the number of sources transitioned. Sources with NULL probation_until are left as-is.
    """
    with conn:
        cur = conn.execute(
            "UPDATE sources SET status='active'"
            " WHERE status='probation'"
            " AND probation_until IS NOT NULL"
            " AND probation_until < datetime('now')"
        )
    return cur.rowcount


def bottom_decile(
    conn: sqlite3.Connection,
    min_items: int = 5,
) -> list[SourceQuality]:
    """Return the worst-scoring sources as drop candidates.

    Calls compute_source_quality to get fresh scores, then filters to sources with
    total_items >= min_items and status != 'probation'.  Returns the bottom 10%
    (at least 1 if any qualify), ordered worst-first.
    """
    all_scores = compute_source_quality(conn)

    eligible = [sq for sq in all_scores if sq.total_items >= min_items and sq.status != "probation"]

    if not eligible:
        return []

    # bottom 10%, at least 1
    n = max(1, math.ceil(len(eligible) * 0.1))
    # eligible is sorted best→worst; take last n and reverse so worst is first
    return list(reversed(eligible[-n:]))
