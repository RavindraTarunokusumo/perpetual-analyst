from __future__ import annotations

import json
import sqlite3

from perpetual_analyst.analyst.schemas import NewObservation, ThesisUpdate, TopicAnalysis
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


def insert_observation(topic_id: int, obs: NewObservation, conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        """INSERT INTO observations (topic_id, kind, content, importance, source_item_ids)
           VALUES (?, ?, ?, ?, ?)""",
        (topic_id, obs.kind, obs.content, obs.importance, json.dumps(obs.source_item_ids)),
    )
    return cur.lastrowid


def get_active_theses(topic_id: int, conn: sqlite3.Connection) -> list[Thesis]:
    rows = conn.execute(
        "SELECT * FROM theses WHERE topic_id = ? AND status = 'active'",
        (topic_id,),
    ).fetchall()
    return [Thesis.from_row(row) for row in rows]


def apply_thesis_update(update: ThesisUpdate, topic_id: int, conn: sqlite3.Connection) -> None:
    if update.thesis_id is None:
        count = conn.execute(
            "SELECT COUNT(*) FROM theses WHERE topic_id = ? AND status = 'active'", (topic_id,)
        ).fetchone()[0]
        if count >= _MAX_ACTIVE_THESES:
            raise ValueError(
                f"Cannot add thesis: {count} active theses already at limit of"
                f" {_MAX_ACTIVE_THESES}"
            )
        cur = conn.execute(
            """INSERT INTO theses (topic_id, statement, rationale, confidence, status)
               VALUES (?, ?, ?, ?, ?)""",
            (
                topic_id,
                update.statement,
                update.change_rationale,
                update.confidence,
                "active",
            ),
        )
        thesis_id = cur.lastrowid
        conn.execute(
            """INSERT INTO thesis_updates (thesis_id, change, confidence_before, confidence_after)
               VALUES (?, ?, ?, ?)""",
            (thesis_id, f"Created: {update.change_rationale}", None, update.confidence),
        )
    else:
        row = conn.execute(
            "SELECT confidence FROM theses WHERE id = ?", (update.thesis_id,)
        ).fetchone()
        confidence_before = row["confidence"] if row else None
        conn.execute(
            """UPDATE theses
               SET statement = ?, confidence = ?, status = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (update.statement, update.confidence, update.new_status, update.thesis_id),
        )
        conn.execute(
            """INSERT INTO thesis_updates (thesis_id, change, confidence_before, confidence_after)
               VALUES (?, ?, ?, ?)""",
            (update.thesis_id, update.change_rationale, confidence_before, update.confidence),
        )


def build_memory_context(topic_id: int, conn: sqlite3.Connection, token_budget: int = 3000) -> str:
    observations = get_active_observations(topic_id, conn)
    char_budget = token_budget * CHARS_PER_TOKEN
    parts: list[str] = []
    used = 0
    for obs in observations:
        line = f"[{obs.kind.upper()}] (importance {obs.importance}) {obs.content}"
        remaining = char_budget - used
        if remaining <= 0:
            break
        if len(line) > remaining:
            parts.append(line[:remaining])
            break
        parts.append(line)
        used += len(line) + 1
    return "\n".join(parts)


def apply_all_memory_writes(
    topic_id: int,
    result: TopicAnalysis,
    conn: sqlite3.Connection,
    analyzed_item_ids: list[int] | None = None,
) -> None:
    with conn:
        for obs in result.new_observations:
            insert_observation(topic_id, obs, conn)
        for update in result.thesis_updates:
            apply_thesis_update(update, topic_id, conn)
        if result.dossier_edits is not None:
            update_dossier(topic_id, result.dossier_edits, conn)
        if analyzed_item_ids:
            placeholders = ",".join("?" for _ in analyzed_item_ids)
            conn.execute(
                f"UPDATE items SET status = 'analyzed' WHERE id IN ({placeholders})",
                analyzed_item_ids,
            )
