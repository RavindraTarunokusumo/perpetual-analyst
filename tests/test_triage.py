from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from perpetual_analyst.analyst.triage import CHUNK_SIZE, triage_items
from perpetual_analyst.config import ModelConfig, Settings
from perpetual_analyst.store.models import Item


@pytest.fixture
def settings():
    return Settings(
        analyst=ModelConfig(id="test-analyst", thinking=False),
        triage=ModelConfig(id="test-triage", thinking=False),
    )


def _client_returning(*payloads: str) -> MagicMock:
    client = MagicMock()
    responses = []
    for payload in payloads:
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = payload
        responses.append(response)
    client.chat.completions.create.side_effect = responses
    return client


def _items_in_db(db, sample_source, n):
    items = []
    for i in range(n):
        cur = db.execute(
            "INSERT INTO items (source_id, content_hash, title, raw_text)" " VALUES (?, ?, ?, ?)",
            (sample_source, f"hash_{i}", f"Item {i}", f"Text {i}"),
        )
        db.commit()
        row = db.execute("SELECT * FROM items WHERE id = ?", (cur.lastrowid,)).fetchone()
        items.append(Item.from_row(row))
    return items


def _payload(items, score):
    return json.dumps(
        [{"item_id": it.id, "score": score, "summary": f"Sum {it.id}"} for it in items]
    )


def test_scores_and_summaries_written(db, sample_source, settings):
    items = _items_in_db(db, sample_source, 2)
    client = _client_returning(_payload(items, 0.7))
    results = triage_items(items, "brief", client, settings, db)
    assert len(results) == 2
    rows = db.execute("SELECT triage_score, triage_summary, status FROM items").fetchall()
    assert all(r["triage_score"] == 0.7 for r in rows)
    assert all(r["status"] == "new" for r in rows)


def test_low_score_marked_skipped(db, sample_source, settings):
    items = _items_in_db(db, sample_source, 2)
    payload = json.dumps(
        [
            {"item_id": items[0].id, "score": 0.1, "summary": "meh"},
            {"item_id": items[1].id, "score": 0.2, "summary": "borderline"},
        ]
    )
    triage_items(items, "brief", _client_returning(payload), settings, db)
    statuses = {r["id"]: r["status"] for r in db.execute("SELECT id, status FROM items").fetchall()}
    assert statuses[items[0].id] == "skipped"
    assert statuses[items[1].id] == "new"


def test_code_fences_stripped(db, sample_source, settings):
    items = _items_in_db(db, sample_source, 1)
    payload = f"```json\n{_payload(items, 0.5)}\n```"
    results = triage_items(items, "brief", _client_returning(payload), settings, db)
    assert len(results) == 1


def test_parse_failure_retries_once_then_gives_up(db, sample_source, settings):
    items = _items_in_db(db, sample_source, 1)
    client = _client_returning("garbage", "more garbage")
    results = triage_items(items, "brief", client, settings, db)
    assert results == []
    assert client.chat.completions.create.call_count == 2
    row = db.execute("SELECT status, triage_score FROM items").fetchone()
    assert row["status"] == "new"
    assert row["triage_score"] is None


def test_retry_succeeds_second_time(db, sample_source, settings):
    items = _items_in_db(db, sample_source, 1)
    client = _client_returning("garbage", _payload(items, 0.9))
    results = triage_items(items, "brief", client, settings, db)
    assert len(results) == 1
    assert client.chat.completions.create.call_count == 2


def test_chunking_splits_calls(db, sample_source, settings):
    items = _items_in_db(db, sample_source, CHUNK_SIZE * 2 + 5)
    chunks = [items[i : i + CHUNK_SIZE] for i in range(0, len(items), CHUNK_SIZE)]
    client = _client_returning(*[_payload(chunk, 0.5) for chunk in chunks])
    results = triage_items(items, "brief", client, settings, db)
    assert len(results) == len(items)
    assert client.chat.completions.create.call_count == 3


def test_unknown_item_id_ignored(db, sample_source, settings):
    items = _items_in_db(db, sample_source, 1)
    payload = json.dumps(
        [
            {"item_id": items[0].id, "score": 0.6, "summary": "ok"},
            {"item_id": 99999, "score": 0.9, "summary": "hallucinated"},
        ]
    )
    results = triage_items(items, "brief", _client_returning(payload), settings, db)
    assert [r.item_id for r in results] == [items[0].id]
