from __future__ import annotations

import sqlite3
from pathlib import Path

_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    telegram_chat_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    brief TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    url TEXT,
    name TEXT,
    active INTEGER DEFAULT 1,
    last_fetched_at TEXT,
    fetch_error_count INTEGER DEFAULT 0,
    quality_score REAL,
    status TEXT DEFAULT 'active',
    probation_until TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS topic_sources (
    topic_id INTEGER REFERENCES topics(id),
    source_id INTEGER REFERENCES sources(id),
    PRIMARY KEY (topic_id, source_id)
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id),
    url TEXT,
    content_hash TEXT UNIQUE,
    title TEXT,
    author TEXT,
    published_at TEXT,
    fetched_at TEXT DEFAULT (datetime('now')),
    raw_text TEXT,
    triage_summary TEXT,
    triage_score REAL,
    status TEXT DEFAULT 'new'
);

CREATE VIRTUAL TABLE IF NOT EXISTS items_fts
    USING fts5(title, raw_text, content='items', content_rowid='id');

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    item_id INTEGER REFERENCES items(id),
    chunk_index INTEGER,
    text TEXT,
    embedding BLOB
);

CREATE TABLE IF NOT EXISTS dossiers (
    topic_id INTEGER PRIMARY KEY REFERENCES topics(id),
    content TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS theses (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER REFERENCES topics(id),
    statement TEXT NOT NULL,
    rationale TEXT,
    confidence REAL,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS thesis_updates (
    id INTEGER PRIMARY KEY,
    thesis_id INTEGER REFERENCES theses(id),
    change TEXT NOT NULL,
    confidence_before REAL,
    confidence_after REAL,
    triggered_by_item_id INTEGER REFERENCES items(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER REFERENCES topics(id),
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    importance INTEGER DEFAULT 2,
    source_item_ids TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts
    USING fts5(content, content='observations', content_rowid='id');

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    report_date TEXT UNIQUE,
    digest_text TEXT,
    full_markdown TEXT,
    delivered_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS citations (
    id INTEGER PRIMARY KEY,
    report_id INTEGER REFERENCES reports(id),
    report_date TEXT,
    item_id INTEGER REFERENCES items(id),
    source_id INTEGER REFERENCES sources(id),
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(report_id, item_id)
);

CREATE TABLE IF NOT EXISTS source_candidates (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER REFERENCES topics(id),
    url TEXT,
    domain TEXT,
    rationale TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(topic_id, url)
);

CREATE TABLE IF NOT EXISTS fts_insufficiencies (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER REFERENCES topics(id),
    query TEXT NOT NULL,
    expected_item_id INTEGER REFERENCES items(id),
    reason TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS items_fts_ai
    AFTER INSERT ON items BEGIN
        INSERT INTO items_fts(rowid, title, raw_text)
        VALUES (new.id, new.title, new.raw_text);
    END;

CREATE TRIGGER IF NOT EXISTS items_fts_au
    AFTER UPDATE ON items BEGIN
        INSERT INTO items_fts(items_fts, rowid, title, raw_text)
        VALUES ('delete', old.id, old.title, old.raw_text);
        INSERT INTO items_fts(rowid, title, raw_text)
        VALUES (new.id, new.title, new.raw_text);
    END;

CREATE TRIGGER IF NOT EXISTS items_fts_ad
    AFTER DELETE ON items BEGIN
        INSERT INTO items_fts(items_fts, rowid, title, raw_text)
        VALUES ('delete', old.id, old.title, old.raw_text);
    END;

CREATE TRIGGER IF NOT EXISTS observations_fts_ai
    AFTER INSERT ON observations BEGIN
        INSERT INTO observations_fts(rowid, content)
        VALUES (new.id, new.content);
    END;

CREATE TRIGGER IF NOT EXISTS observations_fts_au
    AFTER UPDATE ON observations BEGIN
        INSERT INTO observations_fts(observations_fts, rowid, content)
        VALUES ('delete', old.id, old.content);
        INSERT INTO observations_fts(rowid, content)
        VALUES (new.id, new.content);
    END;

CREATE TRIGGER IF NOT EXISTS observations_fts_ad
    AFTER DELETE ON observations BEGIN
        INSERT INTO observations_fts(observations_fts, rowid, content)
        VALUES ('delete', old.id, old.content);
    END;
"""


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Add post-baseline columns if missing (idempotent)."""
    source_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sources)")}
    if "status" not in source_cols:
        conn.execute("ALTER TABLE sources ADD COLUMN status TEXT DEFAULT 'active'")
    if "probation_until" not in source_cols:
        conn.execute("ALTER TABLE sources ADD COLUMN probation_until TEXT")

    candidate_cols = {row["name"] for row in conn.execute("PRAGMA table_info(source_candidates)")}
    if "reviewed_at" not in candidate_cols:
        conn.execute("ALTER TABLE source_candidates ADD COLUMN reviewed_at TEXT")
    if "review_note" not in candidate_cols:
        conn.execute("ALTER TABLE source_candidates ADD COLUMN review_note TEXT")


def init_db(path: str = "data/analyst.db") -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")

    # executescript handles compound statements (BEGIN...END) correctly,
    # but it commits any pending transaction first and sets autocommit.
    conn.executescript(_DDL)
    conn.executescript(_FTS_TRIGGERS)
    _ensure_columns(conn)

    # Seed the default single-user row so FK references to users(id=1) always resolve.
    conn.execute("INSERT OR IGNORE INTO users (id) VALUES (1)")
    conn.commit()
    return conn


def insert_item(
    conn: sqlite3.Connection,
    source_id: int | None,
    content_hash: str,
    title: str | None = None,
    url: str | None = None,
    author: str | None = None,
    published_at: str | None = None,
    raw_text: str | None = None,
) -> bool:
    """Insert item; returns True if inserted, False if content_hash already exists."""
    cur = conn.execute(
        """INSERT OR IGNORE INTO items
           (source_id, content_hash, title, url, author, published_at, raw_text)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (source_id, content_hash, title, url, author, published_at, raw_text),
    )
    return cur.rowcount > 0
