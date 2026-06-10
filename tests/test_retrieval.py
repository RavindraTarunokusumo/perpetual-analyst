"""Tests for retrieval/search.py — FTS5 keyword search helpers."""

from __future__ import annotations

import sqlite3

from perpetual_analyst.retrieval.search import related_items, related_observations
from perpetual_analyst.store.models import Topic


def _insert_observation(
    db: sqlite3.Connection, topic_id: int, content: str, importance: int = 2
) -> int:
    cur = db.execute(
        "INSERT INTO observations (topic_id, kind, content, importance, status)"
        " VALUES (?, 'signal', ?, ?, 'active')",
        (topic_id, content, importance),
    )
    db.commit()
    return cur.lastrowid


def _insert_source(db: sqlite3.Connection, topic_id: int) -> int:
    cur = db.execute("INSERT INTO sources (type, name) VALUES ('rss', 'Test Source')")
    source_id = cur.lastrowid
    db.execute(
        "INSERT INTO topic_sources (topic_id, source_id) VALUES (?, ?)",
        (topic_id, source_id),
    )
    db.commit()
    return source_id


def _insert_item(db: sqlite3.Connection, source_id: int, title: str, raw_text: str) -> int:
    cur = db.execute(
        "INSERT INTO items (source_id, content_hash, title, raw_text)" " VALUES (?, ?, ?, ?)",
        (source_id, f"hash_{title}", title, raw_text),
    )
    db.commit()
    return cur.lastrowid


def test_related_observations_returns_matching(db: sqlite3.Connection, sample_topic: Topic) -> None:
    """An observation whose content contains the query keyword should be returned."""
    _insert_observation(db, sample_topic.id, "AI safety is critically important")
    results = related_observations("safety", sample_topic.id, db, k=5)
    assert len(results) == 1
    assert "safety" in results[0].content


def test_related_observations_empty_on_no_match(
    db: sqlite3.Connection, sample_topic: Topic
) -> None:
    """Query with no matching keyword should return an empty list."""
    _insert_observation(db, sample_topic.id, "AI safety is critically important")
    results = related_observations("cryptocurrency", sample_topic.id, db, k=5)
    assert results == []


def test_related_observations_excludes_other_topics(
    db: sqlite3.Connection, sample_topic: Topic
) -> None:
    """Observations from a different topic should not appear in results."""
    other_cur = db.execute(
        "INSERT INTO topics (user_id, slug, name) VALUES (1, 'other-topic', 'Other')"
    )
    db.commit()
    other_topic_id = other_cur.lastrowid

    _insert_observation(db, other_topic_id, "safety is a concern in other topic")
    _insert_observation(db, sample_topic.id, "finance matters in this topic")

    results = related_observations("safety", sample_topic.id, db, k=5)
    assert results == []


def test_related_items_returns_matching(db: sqlite3.Connection, sample_topic: Topic) -> None:
    """An item whose text contains the query keyword should be returned."""
    source_id = _insert_source(db, sample_topic.id)
    _insert_item(db, source_id, "AI Safety Report", "Detailed analysis of AI safety risks")
    results = related_items("safety", sample_topic.id, db, k=3)
    assert len(results) == 1
    assert results[0].title == "AI Safety Report"


def test_related_items_empty_on_no_match(db: sqlite3.Connection, sample_topic: Topic) -> None:
    """Query with no matching keyword should return an empty list."""
    source_id = _insert_source(db, sample_topic.id)
    _insert_item(db, source_id, "AI Safety Report", "Detailed analysis of AI safety risks")
    results = related_items("cryptocurrency", sample_topic.id, db, k=3)
    assert results == []


def test_related_observations_handles_empty_query(
    db: sqlite3.Connection, sample_topic: Topic
) -> None:
    """Empty query text should return an empty list without raising."""
    _insert_observation(db, sample_topic.id, "Some observation content")
    results = related_observations("", sample_topic.id, db, k=5)
    assert results == []
