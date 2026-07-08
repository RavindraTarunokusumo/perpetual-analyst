from __future__ import annotations

import sqlite3

from perpetual_analyst.analyst.memory import get_dossier, update_dossier


def test_dossier_roundtrip(db: sqlite3.Connection, sample_topic) -> None:
    assert get_dossier(sample_topic.id, db) is None
    update_dossier(sample_topic.id, "## Understanding\nAI is accelerating.", db)
    db.commit()
    assert get_dossier(sample_topic.id, db) == "## Understanding\nAI is accelerating."


def test_dossier_upsert(db: sqlite3.Connection, sample_topic) -> None:
    update_dossier(sample_topic.id, "first", db)
    db.commit()
    update_dossier(sample_topic.id, "second", db)
    db.commit()
    assert get_dossier(sample_topic.id, db) == "second"
