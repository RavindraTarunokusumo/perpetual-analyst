from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from perpetual_analyst.analyst.schemas import NewObservation, TopicAnalysis
from perpetual_analyst.store.db import init_db
from perpetual_analyst.store.models import Item, Topic


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = init_db(":memory:")
    conn.execute("INSERT INTO users (id, telegram_chat_id) VALUES (1, 'test-chat-id')")
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


@pytest.fixture
def mock_openrouter(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    canned_result = TopicAnalysis(
        report_section_markdown="## Test Topic\n\nNothing significant today.",
        new_observations=[
            NewObservation(
                kind="signal", content="Test signal observed.", importance=2, source_item_ids=[1]
            )
        ],
        thesis_updates=[],
        dossier_edits=None,
        open_questions=["What happens next?"],
        watch_next=["Watch source X"],
        nothing_significant=False,
    )

    usage_mock = MagicMock()
    usage_mock.total_tokens = 1234

    response_mock = MagicMock()
    response_mock.parsed = canned_result
    response_mock.usage = usage_mock

    client_mock = MagicMock()
    client_mock.beta.chat.completions.parse.return_value = response_mock

    import perpetual_analyst.analyst.agent as agent_module

    monkeypatch.setattr(agent_module, "make_client", lambda: client_mock)

    return client_mock
