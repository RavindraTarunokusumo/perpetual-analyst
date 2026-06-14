"""Write actions for the dashboard. Each reuses an existing guarded code path."""

from __future__ import annotations

import hashlib
import os
import sqlite3

from perpetual_analyst.delivery.telegram import retry_undelivered
from perpetual_analyst.store.db import insert_item


class NoInboxSource(Exception):
    """No active inbox source linked to the topic."""


def add_inbox_item(
    conn: sqlite3.Connection,
    topic_id: int,
    title: str | None,
    url: str | None,
    text: str,
) -> bool:
    """Insert pasted text as a new inbox item (next run triages it). Silent dedupe."""
    text = (text or "").strip()
    if not text:
        raise ValueError("empty text")
    row = conn.execute(
        """SELECT s.id FROM sources s
           JOIN topic_sources ts ON ts.source_id = s.id
           WHERE ts.topic_id = ? AND s.type = 'inbox' AND s.active = 1
           LIMIT 1""",
        (topic_id,),
    ).fetchone()
    if row is None:
        raise NoInboxSource(f"no inbox source for topic {topic_id}")
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    inserted = insert_item(
        conn,
        source_id=row["id"],
        content_hash=content_hash,
        title=(title or text[:60]).strip(),
        url=url or None,
        raw_text=text,
    )
    conn.commit()
    return inserted


def telegram_configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def retry_all(conn: sqlite3.Connection) -> int:
    return retry_undelivered(conn)
