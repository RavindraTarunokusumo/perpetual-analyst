import sqlite3

import pytest


def test_init_db_creates_all_tables(db: sqlite3.Connection) -> None:
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    tables = {r[0] for r in rows}
    expected = {
        "users",
        "topics",
        "sources",
        "topic_sources",
        "items",
        "chunks",
        "dossiers",
        "theses",
        "thesis_updates",
        "observations",
        "reports",
    }
    assert expected.issubset(tables)


def test_init_db_creates_fts_tables(db: sqlite3.Connection) -> None:
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r[0] for r in rows}
    assert "items_fts" in names
    assert "observations_fts" in names


def test_fts_syncs_on_item_insert(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO sources (id, type) VALUES (1, 'inbox')")
    db.execute(
        "INSERT INTO items (source_id, content_hash, title, raw_text) "
        "VALUES (1, 'hash_fts', 'FTS Title', 'hello searchable world')"
    )
    db.commit()
    results = db.execute(
        "SELECT rowid FROM items_fts WHERE items_fts MATCH 'searchable'"
    ).fetchall()
    assert len(results) == 1


def test_fts_syncs_on_item_delete(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO sources (id, type) VALUES (1, 'inbox')")
    db.execute(
        "INSERT INTO items (source_id, content_hash, title, raw_text) "
        "VALUES (1, 'hash_del', 'Del Title', 'delete me content')"
    )
    db.commit()
    db.execute("DELETE FROM items WHERE content_hash = 'hash_del'")
    db.commit()
    results = db.execute(
        "SELECT rowid FROM items_fts WHERE items_fts MATCH 'delete'",
    ).fetchall()
    assert len(results) == 0


def test_insert_item_deduplicates_by_content_hash(db: sqlite3.Connection) -> None:
    from perpetual_analyst.store.db import insert_item

    db.execute("INSERT INTO sources (id, type) VALUES (1, 'inbox')")
    db.commit()

    inserted = insert_item(db, source_id=1, content_hash="duphash", title="First", raw_text="text")
    db.commit()
    assert inserted is True

    skipped = insert_item(db, source_id=1, content_hash="duphash", title="Second", raw_text="text2")
    db.commit()
    assert skipped is False

    count = db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    assert count == 1


def test_insert_item_plain_raises_on_duplicate(db: sqlite3.Connection) -> None:
    """Documents: plain INSERT raises IntegrityError; callers must use insert_item."""
    import sqlite3 as _sqlite3

    db.execute("INSERT INTO sources (id, type) VALUES (1, 'inbox')")
    db.execute("INSERT INTO items (source_id, content_hash, title) VALUES (1, 'duphash2', 'First')")
    db.commit()
    with pytest.raises(_sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO items (source_id, content_hash, title) VALUES (1, 'duphash2', 'Second')"
        )


def test_foreign_keys_enabled(db: sqlite3.Connection) -> None:
    result = db.execute("PRAGMA foreign_keys").fetchone()
    assert result[0] == 1
