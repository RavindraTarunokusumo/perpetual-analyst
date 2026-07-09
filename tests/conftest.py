from __future__ import annotations

import sqlite3

import pytest

from perpetual_analyst.config import ModelConfig, Settings
from perpetual_analyst.store.db import init_db
from perpetual_analyst.store.models import Item, Topic


@pytest.fixture
def settings() -> Settings:
    return Settings(
        analyst=ModelConfig(id="test-analyst", thinking=False),
        triage=ModelConfig(id="test-triage", thinking=False),
    )


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = init_db(":memory:")
    conn.execute("INSERT OR REPLACE INTO users (id, telegram_chat_id) VALUES (1, 'test-chat-id')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def sample_topic(db: sqlite3.Connection) -> Topic:
    cur = db.execute(
        "INSERT INTO topics (user_id, slug, name, brief)"
        " VALUES (1, 'test-topic', 'Test Topic', 'Track test things')"
    )
    db.commit()
    row = db.execute("SELECT * FROM topics WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Topic.from_row(row)


@pytest.fixture
def sample_source(db: sqlite3.Connection) -> int:
    cur = db.execute("INSERT INTO sources (type, name) VALUES ('inbox', 'Test Inbox')")
    db.commit()
    return cur.lastrowid


@pytest.fixture
def sample_items(db: sqlite3.Connection, sample_topic: Topic, sample_source: int) -> list[Item]:
    items = [
        ("hash_a", "Item Alpha", "Alpha text about AI safety"),
        ("hash_b", "Item Beta", "Beta text about compute scaling"),
        ("hash_c", "Item Gamma", "Gamma text about open weights"),
    ]
    result = []
    for content_hash, title, raw_text in items:
        cur = db.execute(
            "INSERT INTO items (source_id, content_hash, title, raw_text) VALUES (?, ?, ?, ?)",
            (sample_source, content_hash, title, raw_text),
        )
        db.commit()
        row = db.execute("SELECT * FROM items WHERE id = ?", (cur.lastrowid,)).fetchone()
        result.append(Item.from_row(row))
    return result


# ---------------------------------------------------------------------------
# Seeded-database fixtures for the web dashboard tests
# ---------------------------------------------------------------------------


def _seed(path: str) -> None:
    conn = init_db(path)
    conn.execute("INSERT OR REPLACE INTO users (id, telegram_chat_id) VALUES (1, '999')")
    conn.execute(
        "INSERT INTO topics (id, user_id, slug, name, brief, active) "
        "VALUES (1, 1, 'ai-labs', 'AI Frontier Labs', 'frontier model labs', 1)"
    )
    conn.execute(
        "INSERT INTO sources (id, type, url, name, active, last_fetched_at, fetch_error_count) "
        "VALUES (1, 'rss', 'http://x/feed', 'arXiv cs.LG', 1, '2026-06-13 10:00:00', 0)"
    )
    conn.execute(
        "INSERT INTO sources (id, type, url, name, active, fetch_error_count) "
        "VALUES (2, 'inbox', NULL, 'inbox', 1, 0)"
    )
    conn.execute("INSERT INTO topic_sources (topic_id, source_id) VALUES (1, 1), (1, 2)")
    conn.execute(
        "INSERT INTO items (id, source_id, url, content_hash, title, raw_text, "
        "triage_summary, triage_score, status) VALUES "
        "(1, 1, 'http://x/1', 'h1', 'Scaling laws', 'body one', 'a summary', 0.81, 'analyzed')"
    )
    conn.execute(
        "INSERT INTO items (id, source_id, url, content_hash, title, raw_text, "
        "triage_summary, triage_score, status) VALUES "
        "(2, 1, 'http://x/2', 'h2', 'Noise', 'body two', 'low signal', 0.12, 'skipped')"
    )
    conn.execute(
        "INSERT INTO items (id, source_id, content_hash, title, raw_text, status) "
        "VALUES (3, 2, 'h3', 'Pasted note', 'pasted body', 'new')"
    )
    conn.execute(
        "INSERT INTO dossiers (topic_id, content, updated_at) "
        "VALUES (1, '## State of play\nThe frontier is consolidating.', '2026-06-12 09:00:00')"
    )
    conn.execute(
        "INSERT INTO theses (id, topic_id, statement, rationale, confidence, status, "
        "created_at, updated_at) VALUES "
        "(1, 1, 'Open-weight reaches parity', 'why it holds', 0.62, 'active', "
        "'2026-06-01 00:00:00', '2026-06-12 00:00:00')"
    )
    conn.execute(
        "INSERT INTO theses (id, topic_id, statement, rationale, confidence, status) "
        "VALUES (2, 1, 'Retired idea', 'old', 0.30, 'retired')"
    )
    conn.execute(
        "INSERT INTO thesis_updates (id, thesis_id, change, confidence_before, "
        "confidence_after, triggered_by_item_id, created_at) VALUES "
        "(1, 1, 'initial position', NULL, 0.50, NULL, '2026-06-01 00:00:00')"
    )
    conn.execute(
        "INSERT INTO thesis_updates (id, thesis_id, change, confidence_before, "
        "confidence_after, triggered_by_item_id, created_at) VALUES "
        "(2, 1, 'new MoE evidence', 0.50, 0.62, 1, '2026-06-12 00:00:00')"
    )
    conn.execute(
        "INSERT INTO observations (id, topic_id, kind, content, importance, "
        "source_item_ids, status, created_at) VALUES "
        "(1, 1, 'signal', 'New MoE checkpoint released', 3, '[1]', 'active', '2026-06-12 00:00:00')"
    )
    conn.execute(
        "INSERT INTO reports (id, user_id, report_date, digest_text, full_markdown, delivered_at) "
        "VALUES (1, 1, '2026-06-12', 'old digest', '# Old report', '2026-06-12 12:00:00')"
    )
    conn.execute(
        "INSERT INTO reports (id, user_id, report_date, digest_text, full_markdown, delivered_at) "
        "VALUES (2, 1, '2026-06-13', 'new digest', "
        "'# New report\n\nFinding cited [item:1] here.', NULL)"
    )
    conn.commit()
    conn.close()


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "seeded.db")
    _seed(path)
    return path


@pytest.fixture
def empty_db_path(tmp_path):
    path = str(tmp_path / "empty.db")
    init_db(path).close()
    return path


@pytest.fixture
def seeded_conn(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


@pytest.fixture
def client(db_path):
    from perpetual_analyst.web.app import create_app

    app = create_app(db_path)
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture
def empty_client(empty_db_path):
    from perpetual_analyst.web.app import create_app

    app = create_app(empty_db_path)
    app.config.update(TESTING=True)
    return app.test_client()
