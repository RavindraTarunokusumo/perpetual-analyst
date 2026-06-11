from __future__ import annotations

import pytest

from perpetual_analyst.analyst.memory import apply_thesis_update, get_active_theses
from perpetual_analyst.analyst.schemas import ThesisUpdate
from perpetual_analyst.analyst.theses import get_stale_theses, render_thesis_fragment
from perpetual_analyst.store.models import Thesis as ThesisRow
from perpetual_analyst.store.models import ThesisUpdate as ThesisUpdateRow


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


def _insert_thesis(db, topic_id, statement, created_days_ago, updated_days_ago=None):
    updated_expr = (
        f"datetime('now', '-{updated_days_ago} days')" if updated_days_ago is not None else "NULL"
    )
    db.execute(
        f"""INSERT INTO theses (topic_id, statement, confidence, status, created_at, updated_at)
            VALUES (?, ?, 0.5, 'active', datetime('now', '-{created_days_ago} days'),
                    {updated_expr})""",
        (topic_id, statement),
    )
    db.commit()


def test_untouched_31_days_is_stale(db, sample_topic):
    _insert_thesis(db, sample_topic.id, "Old", created_days_ago=31)
    stale = get_stale_theses(sample_topic.id, db)
    assert [t.statement for t in stale] == ["Old"]


def test_untouched_29_days_is_not_stale(db, sample_topic):
    _insert_thesis(db, sample_topic.id, "Fresh-ish", created_days_ago=29)
    assert get_stale_theses(sample_topic.id, db) == []


def test_recent_update_overrides_old_creation(db, sample_topic):
    _insert_thesis(db, sample_topic.id, "Maintained", created_days_ago=60, updated_days_ago=5)
    assert get_stale_theses(sample_topic.id, db) == []


def test_old_update_is_stale(db, sample_topic):
    _insert_thesis(db, sample_topic.id, "Neglected", created_days_ago=60, updated_days_ago=40)
    assert [t.statement for t in get_stale_theses(sample_topic.id, db)] == ["Neglected"]


def test_retired_thesis_never_stale(db, sample_topic):
    _insert_thesis(db, sample_topic.id, "Retired", created_days_ago=90)
    db.execute("UPDATE theses SET status = 'retired'")
    db.commit()
    assert get_stale_theses(sample_topic.id, db) == []


def _thesis_row(statement="Open models reach parity"):
    return ThesisRow(
        id=1,
        topic_id=1,
        statement=statement,
        rationale=None,
        confidence=0.8,
        status="active",
        created_at="2026-06-01",
        updated_at=None,
    )


def _update_row(before, after, change="Third confirming signal this month."):
    return ThesisUpdateRow(
        id=1,
        thesis_id=1,
        change=change,
        confidence_before=before,
        confidence_after=after,
        triggered_by_item_id=None,
        created_at="2026-06-11",
    )


def test_render_empty_returns_empty_string():
    assert render_thesis_fragment([]) == ""


def test_render_shows_confidence_before_after():
    fragment = render_thesis_fragment([(_thesis_row(), _update_row(0.6, 0.8))])
    assert "### Thesis updates" in fragment
    assert "Open models reach parity" in fragment
    assert "0.60 → 0.80" in fragment
    assert "Third confirming signal" in fragment


def test_render_handles_missing_before_confidence():
    fragment = render_thesis_fragment([(_thesis_row(), _update_row(None, 0.5, "Created."))])
    assert "— → 0.50" in fragment
