"""Write actions for the dashboard. Each reuses an existing guarded code path."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from datetime import UTC, datetime

from perpetual_analyst import daily_run
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


_run_lock = threading.Lock()
_run_status: dict = {
    "state": "idle",
    "started_at": None,
    "finished_at": None,
    "error": None,
    "dry_run": False,
}


def run_status() -> dict:
    return dict(_run_status)


def reset_run_status() -> None:
    _run_status.update(state="idle", started_at=None, finished_at=None, error=None, dry_run=False)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _run_worker(db_path: str, dry_run: bool) -> None:
    try:
        # daily_run.main() opens its own conn/client from ANALYST_DB_PATH + env.
        os.environ["ANALYST_DB_PATH"] = db_path
        daily_run.main(dry_run=dry_run)
        _run_status.update(state="done", finished_at=_now())
    except Exception as exc:  # secret hygiene: type name only
        _run_status.update(state="error", finished_at=_now(), error=type(exc).__name__)
    finally:
        _run_lock.release()


def trigger_run(db_path: str, dry_run: bool) -> bool:
    """Start a daily run in a background thread. Returns False if one is in flight."""
    if not _run_lock.acquire(blocking=False):
        return False
    try:
        _run_status.update(
            state="running", started_at=_now(), finished_at=None, error=None, dry_run=dry_run
        )
        thread = threading.Thread(target=_run_worker, args=(db_path, dry_run), daemon=True)
        thread.start()
    except BaseException:
        # If we never handed the lock to a running worker, release it here so the
        # dashboard does not deadlock into a permanent "already in progress" state.
        _run_lock.release()
        raise
    return True
