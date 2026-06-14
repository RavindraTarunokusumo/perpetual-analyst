import sqlite3
import threading
import time

from perpetual_analyst.web import actions


def _conn(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_add_inbox_item_inserts(db_path):
    conn = _conn(db_path)
    ok = actions.add_inbox_item(conn, topic_id=1, title="Note", url=None, text="fresh thought")
    assert ok is True
    row = conn.execute("SELECT * FROM items WHERE raw_text = 'fresh thought'").fetchone()
    assert row["source_id"] == 2  # the inbox source
    assert row["status"] == "new"
    conn.close()


def test_add_inbox_item_dedupes_silently(db_path):
    conn = _conn(db_path)
    assert actions.add_inbox_item(conn, 1, "Note", None, "same text") is True
    assert actions.add_inbox_item(conn, 1, "Note", None, "same text") is False
    conn.close()


def test_add_inbox_item_no_inbox_source_raises(db_path):
    conn = _conn(db_path)
    conn.execute("UPDATE sources SET active = 0 WHERE type = 'inbox'")
    conn.commit()
    try:
        actions.add_inbox_item(conn, 1, "Note", None, "text")
        raised = False
    except actions.NoInboxSource:
        raised = True
    assert raised
    conn.close()


def test_telegram_configured_reads_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert actions.telegram_configured() is False
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "y")
    assert actions.telegram_configured() is True


def test_retry_all_calls_delivery(db_path, monkeypatch):
    calls = {}
    monkeypatch.setattr(actions, "retry_undelivered", lambda conn: calls.setdefault("n", 3))
    conn = _conn(db_path)
    assert actions.retry_all(conn) == 3
    assert calls["n"] == 3
    conn.close()


def test_trigger_run_lock_rejects_concurrent(db_path, monkeypatch):
    gate = threading.Event()

    def fake_run_daily(conn, client, settings, dry_run=False):
        gate.wait(timeout=5)

    monkeypatch.setattr(actions, "run_daily", fake_run_daily)
    monkeypatch.setattr(actions, "make_client", lambda: None)
    monkeypatch.setattr(actions, "load_settings", lambda: None)

    actions.reset_run_status()
    assert actions.trigger_run(db_path, dry_run=True) is True
    for _ in range(50):
        if actions.run_status()["state"] == "running":
            break
        time.sleep(0.02)
    assert actions.trigger_run(db_path, dry_run=True) is False
    gate.set()
    for _ in range(50):
        if actions.run_status()["state"] == "done":
            break
        time.sleep(0.02)
    assert actions.run_status()["state"] == "done"
    # The worker sets state="done" just before releasing the lock in its finally
    # block; wait for the lock to actually free so we don't leak it to the next test.
    for _ in range(50):
        if not actions._run_lock.locked():
            break
        time.sleep(0.02)
    assert not actions._run_lock.locked()


def test_trigger_run_releases_lock_if_thread_fails(db_path, monkeypatch):
    actions.reset_run_status()

    class BoomThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("cannot start thread")

    monkeypatch.setattr(actions.threading, "Thread", BoomThread)
    try:
        actions.trigger_run(db_path, dry_run=True)
        raised = False
    except RuntimeError:
        raised = True
    assert raised
    # the lock must have been released, not stuck in a permanent "in progress" state
    assert actions._run_lock.acquire(blocking=False) is True
    actions._run_lock.release()
