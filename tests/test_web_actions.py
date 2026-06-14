import sqlite3

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
