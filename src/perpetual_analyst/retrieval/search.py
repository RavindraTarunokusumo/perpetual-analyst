"""FTS5 keyword search for the analyst's related-context retrieval. See SPEC §6.

V1 is keyword search only — no vectors. bm25() scores are negative
(more negative = better), so the recency boost multiplies by >1.
"""

from __future__ import annotations

import re
import sqlite3

from perpetual_analyst.store.models import Item, Observation

_MAX_TERMS = 30
_RECENT_BOOST = 1.5


def _fts_query(text: str) -> str:
    """Quote each word so arbitrary text can't inject FTS5 query syntax."""
    terms = re.findall(r"\w+", text)
    return " OR ".join(f'"{term}"' for term in terms[:_MAX_TERMS])


def related_observations(
    text: str, topic_id: int, conn: sqlite3.Connection, k: int = 5
) -> list[Observation]:
    query = _fts_query(text)
    if not query:
        return []
    rows = conn.execute(
        """SELECT o.* FROM observations_fts
           JOIN observations o ON o.id = observations_fts.rowid
           WHERE observations_fts MATCH ? AND o.topic_id = ? AND o.status = 'active'
           ORDER BY bm25(observations_fts)
                    * CASE WHEN o.created_at >= datetime('now', '-30 days')
                           THEN ? ELSE 1.0 END
           LIMIT ?""",
        (query, topic_id, _RECENT_BOOST, k),
    ).fetchall()
    return [Observation.from_row(row) for row in rows]


def related_items(
    text: str,
    topic_id: int,
    conn: sqlite3.Connection,
    k: int = 3,
    exclude_ids: list[int] | None = None,
) -> list[Item]:
    query = _fts_query(text)
    if not query:
        return []
    exclude = exclude_ids or []
    if exclude:
        exclude_clause = f"AND i.id NOT IN ({','.join('?' for _ in exclude)})"
        params: tuple = (topic_id, query, *exclude, _RECENT_BOOST, k)
    else:
        exclude_clause = ""
        params = (topic_id, query, _RECENT_BOOST, k)
    rows = conn.execute(
        f"""SELECT i.* FROM items_fts
            JOIN items i ON i.id = items_fts.rowid
            JOIN topic_sources ts ON ts.source_id = i.source_id AND ts.topic_id = ?
            WHERE items_fts MATCH ? AND i.status != 'skipped'
              {exclude_clause}
            ORDER BY bm25(items_fts)
                     * CASE WHEN i.fetched_at >= datetime('now', '-14 days')
                            THEN ? ELSE 1.0 END
            LIMIT ?""",
        params,
    ).fetchall()
    return [Item.from_row(row) for row in rows]
