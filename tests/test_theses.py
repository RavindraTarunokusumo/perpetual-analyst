from __future__ import annotations

import pytest

from perpetual_analyst.analyst.memory import apply_thesis_update, get_active_theses
from perpetual_analyst.analyst.schemas import ThesisUpdate


def _update(
    thesis_id=None,
    statement="Open-weight models reach frontier parity",
    confidence=0.6,
    rationale="initial signal",
    status="active",
):
    return ThesisUpdate(
        thesis_id=thesis_id,
        statement=statement,
        confidence=confidence,
        change_rationale=rationale,
        new_status=status,
    )


def test_create_thesis_writes_audit_row(db, sample_topic):
    apply_thesis_update(_update(), sample_topic.id, db)
    theses = get_active_theses(sample_topic.id, db)
    assert len(theses) == 1
    audit = db.execute(
        "SELECT * FROM thesis_updates WHERE thesis_id = ?", (theses[0].id,)
    ).fetchall()
    assert len(audit) == 1
    assert audit[0]["confidence_before"] is None
    assert audit[0]["confidence_after"] == 0.6


def test_revise_thesis_logs_before_after(db, sample_topic):
    apply_thesis_update(_update(), sample_topic.id, db)
    thesis = get_active_theses(sample_topic.id, db)[0]
    apply_thesis_update(
        _update(thesis_id=thesis.id, confidence=0.8, rationale="third confirming signal"),
        sample_topic.id,
        db,
    )
    audit = db.execute(
        "SELECT * FROM thesis_updates WHERE thesis_id = ? ORDER BY id", (thesis.id,)
    ).fetchall()
    assert len(audit) == 2
    assert audit[1]["confidence_before"] == 0.6
    assert audit[1]["confidence_after"] == 0.8


def test_retire_thesis_removes_from_active(db, sample_topic):
    apply_thesis_update(_update(), sample_topic.id, db)
    thesis = get_active_theses(sample_topic.id, db)[0]
    apply_thesis_update(
        _update(thesis_id=thesis.id, status="retired", rationale="disproven by filing"),
        sample_topic.id,
        db,
    )
    assert get_active_theses(sample_topic.id, db) == []
    status = db.execute("SELECT status FROM theses WHERE id = ?", (thesis.id,)).fetchone()["status"]
    assert status == "retired"


def test_eighth_active_thesis_raises(db, sample_topic):
    for i in range(7):
        apply_thesis_update(_update(statement=f"Thesis {i}"), sample_topic.id, db)
    with pytest.raises(ValueError, match="limit"):
        apply_thesis_update(_update(statement="Thesis 8"), sample_topic.id, db)
