"""Tests for analyst/triage.py — relevance triage pass."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock

from perpetual_analyst.analyst.triage import triage_items
from perpetual_analyst.config import ModelConfig, Settings
from perpetual_analyst.store.models import Item


def _make_settings() -> Settings:
    return Settings(
        analyst=ModelConfig(id="anthropic/claude-opus-4-8", thinking=True),
        triage=ModelConfig(id="deepseek/deepseek-v4-flash", thinking=False),
    )


def _make_client(scores: list[dict]) -> MagicMock:
    """Return a mock openai client whose triage call returns the given scores."""
    response_content = json.dumps(scores)
    message_mock = MagicMock()
    message_mock.content = response_content
    choice_mock = MagicMock()
    choice_mock.message = message_mock
    response_mock = MagicMock()
    response_mock.choices = [choice_mock]
    client_mock = MagicMock()
    client_mock.chat.completions.create.return_value = response_mock
    return client_mock


def test_triage_items_marks_low_score_as_skipped(
    db: sqlite3.Connection, sample_items: list[Item]
) -> None:
    """Items with score < 0.2 should have status='skipped' in the DB."""
    item = sample_items[0]
    scores = [{"item_id": item.id, "score": 0.1, "summary": "Not relevant."}]
    client = _make_client(scores)
    triage_items([item], "AI safety brief", client, _make_settings(), db)
    row = db.execute("SELECT status FROM items WHERE id = ?", (item.id,)).fetchone()
    assert row["status"] == "skipped"


def test_triage_items_marks_high_score_as_analyzed(
    db: sqlite3.Connection, sample_items: list[Item]
) -> None:
    """Items with score >= 0.2 should have status='analyzed' in the DB."""
    item = sample_items[0]
    scores = [{"item_id": item.id, "score": 0.8, "summary": "Very relevant."}]
    client = _make_client(scores)
    triage_items([item], "AI safety brief", client, _make_settings(), db)
    row = db.execute("SELECT status FROM items WHERE id = ?", (item.id,)).fetchone()
    assert row["status"] == "analyzed"


def test_triage_items_returns_only_relevant(
    db: sqlite3.Connection, sample_items: list[Item]
) -> None:
    """Only items with score >= 0.2 should be returned."""
    item_a, item_b = sample_items[0], sample_items[1]
    scores = [
        {"item_id": item_a.id, "score": 0.1, "summary": "Not relevant."},
        {"item_id": item_b.id, "score": 0.9, "summary": "Highly relevant."},
    ]
    client = _make_client(scores)
    result = triage_items([item_a, item_b], "AI safety brief", client, _make_settings(), db)
    assert len(result) == 1
    assert result[0].id == item_b.id


def test_triage_items_graceful_on_api_failure(
    db: sqlite3.Connection, sample_items: list[Item]
) -> None:
    """If the API call raises, all items should be returned unchanged."""
    client = MagicMock()
    client.chat.completions.create.side_effect = Exception("API down")
    result = triage_items(sample_items, "brief", client, _make_settings(), db)
    assert len(result) == len(sample_items)


def test_triage_items_stores_summary(db: sqlite3.Connection, sample_items: list[Item]) -> None:
    """triage_summary should be written to the DB for scored items."""
    item = sample_items[0]
    scores = [{"item_id": item.id, "score": 0.5, "summary": "Moderately relevant piece."}]
    client = _make_client(scores)
    triage_items([item], "AI safety brief", client, _make_settings(), db)
    row = db.execute("SELECT triage_summary FROM items WHERE id = ?", (item.id,)).fetchone()
    assert row["triage_summary"] == "Moderately relevant piece."
