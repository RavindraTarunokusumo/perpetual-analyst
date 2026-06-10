"""Tests for analyst/compaction.py — observation expiry by importance/age. See SPEC §8."""

from __future__ import annotations

import sqlite3

from perpetual_analyst.analyst.compaction import expire_observations
from perpetual_analyst.store.models import Topic


def _insert_obs(
    db: sqlite3.Connection,
    topic_id: int,
    importance: int = 2,
    status: str = "active",
) -> int:
    cur = db.execute(
        "INSERT INTO observations (topic_id, kind, content, importance, status)"
        " VALUES (?, 'signal', 'test content', ?, ?)",
        (topic_id, importance, status),
    )
    db.commit()
    return cur.lastrowid


def test_importance1_old_expires(db: sqlite3.Connection, sample_topic: Topic) -> None:
    """importance-1 observation backdated 31 days should become expired."""
    obs_id = _insert_obs(db, sample_topic.id, importance=1)
    db.execute(
        "UPDATE observations SET created_at = datetime('now', '-31 days') WHERE id = ?",
        (obs_id,),
    )
    db.commit()

    changed = expire_observations(db)

    assert changed == 1
    row = db.execute("SELECT status FROM observations WHERE id = ?", (obs_id,)).fetchone()
    assert row["status"] == "expired"


def test_importance1_recent_stays_active(db: sqlite3.Connection, sample_topic: Topic) -> None:
    """importance-1 observation backdated only 29 days should remain active."""
    obs_id = _insert_obs(db, sample_topic.id, importance=1)
    db.execute(
        "UPDATE observations SET created_at = datetime('now', '-29 days') WHERE id = ?",
        (obs_id,),
    )
    db.commit()

    changed = expire_observations(db)

    assert changed == 0
    row = db.execute("SELECT status FROM observations WHERE id = ?", (obs_id,)).fetchone()
    assert row["status"] == "active"


def test_importance2_old_expires(db: sqlite3.Connection, sample_topic: Topic) -> None:
    """importance-2 observation backdated 91 days should become expired."""
    obs_id = _insert_obs(db, sample_topic.id, importance=2)
    db.execute(
        "UPDATE observations SET created_at = datetime('now', '-91 days') WHERE id = ?",
        (obs_id,),
    )
    db.commit()

    changed = expire_observations(db)

    assert changed == 1
    row = db.execute("SELECT status FROM observations WHERE id = ?", (obs_id,)).fetchone()
    assert row["status"] == "expired"


def test_importance2_recent_stays_active(db: sqlite3.Connection, sample_topic: Topic) -> None:
    """importance-2 observation backdated only 89 days should remain active."""
    obs_id = _insert_obs(db, sample_topic.id, importance=2)
    db.execute(
        "UPDATE observations SET created_at = datetime('now', '-89 days') WHERE id = ?",
        (obs_id,),
    )
    db.commit()

    changed = expire_observations(db)

    assert changed == 0
    row = db.execute("SELECT status FROM observations WHERE id = ?", (obs_id,)).fetchone()
    assert row["status"] == "active"


def test_importance3_never_expires(db: sqlite3.Connection, sample_topic: Topic) -> None:
    """importance-3 observation backdated 200 days should remain active (immune)."""
    obs_id = _insert_obs(db, sample_topic.id, importance=3)
    db.execute(
        "UPDATE observations SET created_at = datetime('now', '-200 days') WHERE id = ?",
        (obs_id,),
    )
    db.commit()

    changed = expire_observations(db)

    assert changed == 0
    row = db.execute("SELECT status FROM observations WHERE id = ?", (obs_id,)).fetchone()
    assert row["status"] == "active"


def test_promoted_observation_untouched(db: sqlite3.Connection, sample_topic: Topic) -> None:
    """A 'promoted' observation backdated 200 days should not be touched."""
    obs_id = _insert_obs(db, sample_topic.id, importance=1, status="promoted")
    db.execute(
        "UPDATE observations SET created_at = datetime('now', '-200 days') WHERE id = ?",
        (obs_id,),
    )
    db.commit()

    changed = expire_observations(db)

    assert changed == 0
    row = db.execute("SELECT status FROM observations WHERE id = ?", (obs_id,)).fetchone()
    assert row["status"] == "promoted"


def test_return_value_equals_expired_count(db: sqlite3.Connection, sample_topic: Topic) -> None:
    """Return value should equal the exact number of rows transitioned to expired."""
    ids = [_insert_obs(db, sample_topic.id, importance=1) for _ in range(3)]
    for obs_id in ids:
        db.execute(
            "UPDATE observations SET created_at = datetime('now', '-31 days') WHERE id = ?",
            (obs_id,),
        )
    db.commit()

    changed = expire_observations(db)

    assert changed == 3


def test_topic_id_filter_isolates_topic(db: sqlite3.Connection, sample_topic: Topic) -> None:
    """When topic_id is given, only observations in that topic are expired."""
    # Insert a second topic
    cur = db.execute(
        "INSERT INTO topics (user_id, slug, name, brief)"
        " VALUES (1, 'other-topic', 'Other Topic', 'Other brief')"
    )
    db.commit()
    other_topic_id = cur.lastrowid

    obs_target = _insert_obs(db, sample_topic.id, importance=1)
    obs_other = _insert_obs(db, other_topic_id, importance=1)

    for obs_id in (obs_target, obs_other):
        db.execute(
            "UPDATE observations SET created_at = datetime('now', '-31 days') WHERE id = ?",
            (obs_id,),
        )
    db.commit()

    changed = expire_observations(db, topic_id=sample_topic.id)

    assert changed == 1
    assert (
        db.execute("SELECT status FROM observations WHERE id = ?", (obs_target,)).fetchone()[
            "status"
        ]
        == "expired"
    )
    assert (
        db.execute("SELECT status FROM observations WHERE id = ?", (obs_other,)).fetchone()[
            "status"
        ]
        == "active"
    )
