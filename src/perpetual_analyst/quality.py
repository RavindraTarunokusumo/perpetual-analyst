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
    uniqueness_rate: float
    freshness_lead_rate: float
    score: float
    status: str


def compute_source_quality(conn: sqlite3.Connection) -> list[SourceQuality]:
    """Compute and persist quality_score for every source that has at least one item.

    For each source:
      hit_rate      = items with triage_score >= TRIAGE_HIT_THRESHOLD / total_items
      citation_rate = COUNT(DISTINCT cited item_id) / total_items  (capped at 1.0)
      uniqueness_rate     = share of cited reports where this is the only cited source
      freshness_lead_rate = share of cited reports where this source has the earliest item
      score = hit_rate

    Writes quality_score back to sources in a single transaction.

    Returns a list of SourceQuality ordered by score descending.
    """
    cited_report_counts: dict[int, int] = {}
    unique_report_counts: dict[int, int] = {}
    freshness_lead_counts: dict[int, int] = {}

    citation_groups = conn.execute(
        """
        SELECT c.report_id, c.report_date, c.source_id, i.published_at
        FROM citations c
        JOIN items i ON i.id = c.item_id
        WHERE c.source_id IS NOT NULL
          AND (c.report_id IS NOT NULL OR c.report_date IS NOT NULL)
        """
    ).fetchall()
    by_report: dict[tuple[int | None, str | None], list[sqlite3.Row]] = {}
    for row in citation_groups:
        by_report.setdefault((row["report_id"], row["report_date"]), []).append(row)

    for rows_for_report in by_report.values():
        source_ids = {int(row["source_id"]) for row in rows_for_report if row["source_id"]}
        for source_id in source_ids:
            cited_report_counts[source_id] = cited_report_counts.get(source_id, 0) + 1
        if len(source_ids) == 1:
            source_id = next(iter(source_ids))
            unique_report_counts[source_id] = unique_report_counts.get(source_id, 0) + 1

        published_values = [
            row["published_at"] for row in rows_for_report if row["published_at"]
        ]
        if published_values:
            earliest = min(published_values)
            lead_sources = {
                int(row["source_id"])
                for row in rows_for_report
                if row["source_id"] and row["published_at"] == earliest
            }
            for source_id in lead_sources:
                freshness_lead_counts[source_id] = freshness_lead_counts.get(source_id, 0) + 1

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

    for row in rows:
        total = row["total_items"]
        if total == 0:
            continue

        hit_rate = row["hits"] / total
        citation_rate = min(row["cited"] / total, 1.0)
        cited_reports = cited_report_counts.get(row["source_id"], 0)
        uniqueness_rate = (
            unique_report_counts.get(row["source_id"], 0) / cited_reports
            if cited_reports
            else 0.0
        )
        freshness_lead_rate = (
            freshness_lead_counts.get(row["source_id"], 0) / cited_reports
            if cited_reports
            else 0.0
        )
        # citation/uniqueness/freshness weights retired (citations table unpopulated post-Nexus); reserved for a third-party source-rating API — see TODO backlog  # noqa: E501
        score = round(hit_rate, 4)

        results.append(
            SourceQuality(
                source_id=row["source_id"],
                name=row["name"],
                total_items=total,
                hit_rate=hit_rate,
                citation_rate=citation_rate,
                uniqueness_rate=uniqueness_rate,
                freshness_lead_rate=freshness_lead_rate,
                score=score,
                status=row["status"] or "active",
            )
        )

    with conn:
        conn.executemany(
            "UPDATE sources SET quality_score = ? WHERE id = ?",
            [(sq.score, sq.source_id) for sq in results],
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
    all_scores: list[SourceQuality] | None = None,
) -> list[SourceQuality]:
    """Return the worst-scoring sources as drop candidates.

    Filters to sources with total_items >= min_items and status != 'probation', then
    returns the bottom 10% (at least 1 if any qualify), ordered worst-first. Pass
    `all_scores` (from a prior compute_source_quality call) to avoid recomputing.
    """
    if all_scores is None:
        all_scores = compute_source_quality(conn)

    eligible = sorted(
        (sq for sq in all_scores if sq.total_items >= min_items and sq.status != "probation"),
        key=lambda sq: sq.score,  # worst-first
    )
    if not eligible:
        return []

    n = max(1, math.ceil(len(eligible) * 0.1))
    return eligible[:n]
