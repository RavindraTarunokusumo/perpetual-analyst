"""Tests for analyst/theses.py — stale-flagging and rendering."""

from __future__ import annotations

import sqlite3

from perpetual_analyst.analyst.theses import get_stale_theses, render_thesis_fragment
from perpetual_analyst.store.models import Topic


def _insert_thesis(
    db: sqlite3.Connection, topic_id: int, statement: str, confidence: float = 0.7
) -> int:
    cur = db.execute(
        "INSERT INTO theses (topic_id, statement, confidence, status) VALUES (?, ?, ?, 'active')",
        (topic_id, statement, confidence),
    )
    db.commit()
    return cur.lastrowid


def test_get_stale_theses_returns_empty_when_no_stale(
    db: sqlite3.Connection, sample_topic: Topic
) -> None:
    """A freshly inserted thesis should NOT appear as stale."""
    _insert_thesis(db, sample_topic.id, "Fresh thesis")
    stale = get_stale_theses(sample_topic.id, db, days=30)
    assert stale == []


def test_get_stale_theses_returns_old_thesis(db: sqlite3.Connection, sample_topic: Topic) -> None:
    """A thesis backdated >30 days should appear in stale results."""
    thesis_id = _insert_thesis(db, sample_topic.id, "Old thesis")
    db.execute(
        "UPDATE theses SET updated_at = datetime('now', '-40 days') WHERE id = ?",
        (thesis_id,),
    )
    db.commit()
    stale = get_stale_theses(sample_topic.id, db, days=30)
    assert len(stale) == 1
    assert stale[0].id == thesis_id


def test_render_thesis_fragment_empty(db: sqlite3.Connection, sample_topic: Topic) -> None:
    """With no theses, render_thesis_fragment returns the sentinel string."""
    fragment = render_thesis_fragment(sample_topic.id, db)
    assert fragment == "(no active theses)"


def test_render_thesis_fragment_shows_confidence(
    db: sqlite3.Connection, sample_topic: Topic
) -> None:
    """Confidence should be shown as a percentage in the fragment."""
    _insert_thesis(db, sample_topic.id, "AI will transform work", confidence=0.75)
    fragment = render_thesis_fragment(sample_topic.id, db)
    assert "75%" in fragment
    assert "AI will transform work" in fragment


def test_render_thesis_fragment_marks_stale(db: sqlite3.Connection, sample_topic: Topic) -> None:
    """Backdated thesis should have '(stale)' in its fragment line."""
    thesis_id = _insert_thesis(db, sample_topic.id, "Stale insight", confidence=0.6)
    db.execute(
        "UPDATE theses SET updated_at = datetime('now', '-40 days') WHERE id = ?",
        (thesis_id,),
    )
    db.commit()
    fragment = render_thesis_fragment(sample_topic.id, db)
    assert "(stale)" in fragment
