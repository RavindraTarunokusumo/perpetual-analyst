import sqlite3
import pytest
from perpetual_analyst.store.db import init_db


def test_init_db_creates_all_tables(db: sqlite3.Connection) -> None:
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    tables = {r[0] for r in rows}
    expected = {
        "users", "topics", "sources", "topic_sources",
        "items", "chunks", "dossiers", "theses", "thesis_updates",
        "observations", "reports",
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


def test_content_hash_deduplication(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO sources (id, type) VALUES (1, 'inbox')")
    db.execute(
        "INSERT INTO items (source_id, content_hash, title, raw_text) "
        "VALUES (1, 'duphash', 'First', 'text')"
    )
    db.execute(
        "INSERT OR IGNORE INTO items (source_id, content_hash, title, raw_text) "
        "VALUES (1, 'duphash', 'Second', 'text2')"
    )
    db.commit()
    count = db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    assert count == 1


def test_foreign_keys_enabled(db: sqlite3.Connection) -> None:
    result = db.execute("PRAGMA foreign_keys").fetchone()
    assert result[0] == 1
