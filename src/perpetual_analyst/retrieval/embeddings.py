from __future__ import annotations

import importlib.util
import sqlite3
from dataclasses import dataclass

from perpetual_analyst.config import Settings


@dataclass
class EmbeddingGateStatus:
    enabled: bool
    available: bool
    reason: str


def record_fts_insufficiency(
    conn: sqlite3.Connection,
    topic_id: int,
    query: str,
    reason: str,
    expected_item_id: int | None = None,
) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO fts_insufficiencies
                   (topic_id, query, expected_item_id, reason)
               VALUES (?, ?, ?, ?)""",
            (topic_id, query, expected_item_id, reason),
        )
    return int(cur.lastrowid)


def has_recorded_fts_insufficiency(
    conn: sqlite3.Connection,
    topic_id: int | None = None,
) -> bool:
    if topic_id is None:
        row = conn.execute("SELECT 1 FROM fts_insufficiencies LIMIT 1").fetchone()
    else:
        row = conn.execute(
            "SELECT 1 FROM fts_insufficiencies WHERE topic_id = ? LIMIT 1",
            (topic_id,),
        ).fetchone()
    return row is not None


def _missing_optional_modules() -> list[str]:
    missing = []
    for module in ("sqlite_vec", "voyageai"):
        if importlib.util.find_spec(module) is None:
            missing.append(module)
    return missing


def embedding_gate_status(
    settings: Settings,
    conn: sqlite3.Connection,
    topic_id: int | None = None,
) -> EmbeddingGateStatus:
    retrieval = settings.retrieval
    if not retrieval.embeddings_enabled:
        return EmbeddingGateStatus(
            enabled=False,
            available=False,
            reason="Embeddings are disabled in settings.",
        )

    if retrieval.require_fts_failure and not has_recorded_fts_insufficiency(conn, topic_id):
        return EmbeddingGateStatus(
            enabled=True,
            available=False,
            reason="Embeddings require a recorded FTS insufficiency before activation.",
        )

    missing = _missing_optional_modules()
    if missing:
        return EmbeddingGateStatus(
            enabled=True,
            available=False,
            reason=f"Missing optional embedding dependencies: {', '.join(missing)}.",
        )

    return EmbeddingGateStatus(
        enabled=True,
        available=True,
        reason=f"{retrieval.embeddings_provider}:{retrieval.embedding_model} is available.",
    )
