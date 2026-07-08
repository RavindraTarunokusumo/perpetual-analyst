from __future__ import annotations

import json
import sqlite3

from perpetual_analyst.store.models import Observation, Thesis

CHARS_PER_TOKEN: int = 4
_MAX_ACTIVE_THESES: int = 7


def get_dossier(topic_id: int, conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT content FROM dossiers WHERE topic_id = ?", (topic_id,)).fetchone()
    return row["content"] if row else None


def update_dossier(topic_id: int, content: str, conn: sqlite3.Connection) -> None:
    conn.execute(
        """INSERT INTO dossiers (topic_id, content, updated_at)
           VALUES (?, ?, datetime('now'))
           ON CONFLICT(topic_id) DO UPDATE
           SET content = excluded.content, updated_at = excluded.updated_at""",
        (topic_id, content),
    )


def get_active_observations(topic_id: int, conn: sqlite3.Connection) -> list[Observation]:
    rows = conn.execute(
        """SELECT * FROM observations
           WHERE topic_id = ? AND status = 'active'
           ORDER BY importance DESC, created_at DESC""",
        (topic_id,),
    ).fetchall()
    return [Observation.from_row(row) for row in rows]


def insert_observation(
    topic_id: int,
    kind: str,
    content: str,
    importance: int,
    conn: sqlite3.Connection,
    source_item_ids: list[int] | None = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO observations (topic_id, kind, content, importance, source_item_ids)
           VALUES (?, ?, ?, ?, ?)""",
        (topic_id, kind, content, importance, json.dumps(source_item_ids or [])),
    )
    return cur.lastrowid


def get_active_theses(topic_id: int, conn: sqlite3.Connection) -> list[Thesis]:
    rows = conn.execute(
        "SELECT * FROM theses WHERE topic_id = ? AND status = 'active'",
        (topic_id,),
    ).fetchall()
    return [Thesis.from_row(row) for row in rows]


def apply_thesis_update(
    topic_id: int,
    conn: sqlite3.Connection,
    *,
    thesis_id: int | None,
    statement: str,
    confidence: float,
    change_rationale: str,
    new_status: str = "active",
) -> None:
    if thesis_id is None:
        count = conn.execute(
            "SELECT COUNT(*) FROM theses WHERE topic_id = ? AND status = 'active'", (topic_id,)
        ).fetchone()[0]
        if count >= _MAX_ACTIVE_THESES:
            raise ValueError(
                f"Cannot add thesis: {count} active theses already at limit of {_MAX_ACTIVE_THESES}"
            )
        cur = conn.execute(
            """INSERT INTO theses (topic_id, statement, rationale, confidence, status)
               VALUES (?, ?, ?, ?, ?)""",
            (
                topic_id,
                statement,
                change_rationale,
                confidence,
                "active",
            ),
        )
        new_thesis_id = cur.lastrowid
        conn.execute(
            """INSERT INTO thesis_updates (thesis_id, change, confidence_before, confidence_after)
               VALUES (?, ?, ?, ?)""",
            (new_thesis_id, f"Created: {change_rationale}", None, confidence),
        )
    else:
        row = conn.execute("SELECT confidence FROM theses WHERE id = ?", (thesis_id,)).fetchone()
        confidence_before = row["confidence"] if row else None
        conn.execute(
            """UPDATE theses
               SET statement = ?, confidence = ?, status = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (statement, confidence, new_status, thesis_id),
        )
        conn.execute(
            """INSERT INTO thesis_updates (thesis_id, change, confidence_before, confidence_after)
               VALUES (?, ?, ?, ?)""",
            (thesis_id, change_rationale, confidence_before, confidence),
        )
