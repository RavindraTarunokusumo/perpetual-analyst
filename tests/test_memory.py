from __future__ import annotations

import sqlite3

import pytest

from perpetual_analyst.analyst.memory import (
    CHARS_PER_TOKEN,
    apply_all_memory_writes,
    build_memory_context,
    get_active_observations,
    get_active_theses,
    get_dossier,
    insert_observation,
    update_dossier,
)
from perpetual_analyst.analyst.schemas import NewObservation, ThesisUpdate, TopicAnalysis


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


def test_insert_observation(db: sqlite3.Connection, sample_topic) -> None:
    obs = NewObservation(
        kind="signal", content="GPT-5 rumoured.", importance=3, source_item_ids=[1, 2]
    )
    row_id = insert_observation(sample_topic.id, obs, db)
    db.commit()
    assert row_id > 0
    active = get_active_observations(sample_topic.id, db)
    assert len(active) == 1
    assert active[0].content == "GPT-5 rumoured."
    assert active[0].importance == 3


def test_build_memory_context_respects_budget(db: sqlite3.Connection, sample_topic) -> None:
    for i in range(10):
        obs = NewObservation(
            kind="fact",
            content="A" * 200,
            importance=2,
            source_item_ids=[],
        )
        insert_observation(sample_topic.id, obs, db)
    db.commit()

    context = build_memory_context(sample_topic.id, db, token_budget=100)
    assert len(context) <= 100 * CHARS_PER_TOKEN + 50


def test_build_memory_context_sorts_by_importance(db: sqlite3.Connection, sample_topic) -> None:
    insert_observation(
        sample_topic.id,
        NewObservation(kind="fact", content="Minor note.", importance=1, source_item_ids=[]),
        db,
    )
    insert_observation(
        sample_topic.id,
        NewObservation(kind="signal", content="Critical signal.", importance=3, source_item_ids=[]),
        db,
    )
    insert_observation(
        sample_topic.id,
        NewObservation(
            kind="pattern", content="Notable pattern.", importance=2, source_item_ids=[]
        ),
        db,
    )
    db.commit()

    context = build_memory_context(sample_topic.id, db, token_budget=10000)
    critical_pos = context.index("Critical signal.")
    notable_pos = context.index("Notable pattern.")
    minor_pos = context.index("Minor note.")
    assert critical_pos < notable_pos < minor_pos


def test_apply_thesis_update_creates_new(db: sqlite3.Connection, sample_topic) -> None:
    from perpetual_analyst.analyst.memory import apply_thesis_update

    update = ThesisUpdate(
        thesis_id=None,
        statement="Open weights will reach frontier parity.",
        confidence=0.7,
        change_rationale="Three strong signals this week.",
        new_status="active",
    )
    apply_thesis_update(update, sample_topic.id, db)
    db.commit()

    theses = get_active_theses(sample_topic.id, db)
    assert len(theses) == 1
    assert theses[0].confidence == 0.7

    audit = db.execute(
        "SELECT * FROM thesis_updates WHERE thesis_id = ?", (theses[0].id,)
    ).fetchall()
    assert len(audit) == 1


def test_apply_thesis_update_writes_audit_trail(db: sqlite3.Connection, sample_topic) -> None:
    from perpetual_analyst.analyst.memory import apply_thesis_update

    create = ThesisUpdate(
        thesis_id=None, statement="S", confidence=0.5, change_rationale="init", new_status="active"
    )
    apply_thesis_update(create, sample_topic.id, db)
    db.commit()
    thesis_id = get_active_theses(sample_topic.id, db)[0].id

    revise = ThesisUpdate(
        thesis_id=thesis_id,
        statement="S revised",
        confidence=0.8,
        change_rationale="new evidence",
        new_status="active",
    )
    apply_thesis_update(revise, sample_topic.id, db)
    db.commit()

    audit_rows = db.execute(
        "SELECT * FROM thesis_updates WHERE thesis_id = ?", (thesis_id,)
    ).fetchall()
    assert len(audit_rows) == 2
    last = audit_rows[-1]
    assert last["confidence_before"] == pytest.approx(0.5)
    assert last["confidence_after"] == pytest.approx(0.8)


def test_thesis_limit_enforced(db: sqlite3.Connection, sample_topic) -> None:
    from perpetual_analyst.analyst.memory import apply_thesis_update

    for i in range(7):
        apply_thesis_update(
            ThesisUpdate(
                thesis_id=None,
                statement=f"Thesis {i}",
                confidence=0.5,
                change_rationale="init",
                new_status="active",
            ),
            sample_topic.id,
            db,
        )
    db.commit()

    with pytest.raises(ValueError, match="active theses"):
        apply_thesis_update(
            ThesisUpdate(
                thesis_id=None,
                statement="Eighth thesis",
                confidence=0.5,
                change_rationale="overflow",
                new_status="active",
            ),
            sample_topic.id,
            db,
        )


def test_apply_all_memory_writes_is_atomic(db: sqlite3.Connection, sample_topic) -> None:
    result = TopicAnalysis(
        report_section_markdown="# Section",
        new_observations=[
            NewObservation(kind="fact", content="Atomic fact.", importance=2, source_item_ids=[])
        ],
        thesis_updates=[
            ThesisUpdate(
                thesis_id=None,
                statement="Atomic thesis.",
                confidence=0.6,
                change_rationale="test",
                new_status="active",
            )
        ],
        dossier_edits="Updated dossier content.",
        open_questions=[],
        watch_next=[],
        nothing_significant=False,
    )
    apply_all_memory_writes(sample_topic.id, result, db)

    assert len(get_active_observations(sample_topic.id, db)) == 1
    assert len(get_active_theses(sample_topic.id, db)) == 1
    assert get_dossier(sample_topic.id, db) == "Updated dossier content."
