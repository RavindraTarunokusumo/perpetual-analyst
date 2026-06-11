"""Tests for citation recording — Phase 5 Task B."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from perpetual_analyst.analyst.schemas import TopicAnalysis
from perpetual_analyst.report.assemble import assemble_report
from perpetual_analyst.report.render import cited_item_ids
from perpetual_analyst.store.models import Item

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client(digest_text: str = "<b>Digest</b>") -> MagicMock:
    response_mock = MagicMock()
    response_mock.choices[0].message.content = digest_text
    client_mock = MagicMock()
    client_mock.chat.completions.create.return_value = response_mock
    return client_mock


def _make_settings() -> MagicMock:
    settings = MagicMock()
    settings.analyst.id = "test-model"
    return settings


def _make_analysis(
    markdown: str = "## Topic\n\nContent",
    nothing_significant: bool = False,
) -> TopicAnalysis:
    return TopicAnalysis(
        report_section_markdown=markdown if not nothing_significant else "",
        new_observations=[],
        thesis_updates=[],
        dossier_edits=None,
        open_questions=[],
        watch_next=[],
        nothing_significant=nothing_significant,
    )


# ---------------------------------------------------------------------------
# cited_item_ids unit tests
# ---------------------------------------------------------------------------


def test_cited_item_ids_returns_unique_in_order() -> None:
    """Returns unique ids in document (first-occurrence) order."""
    md = "See [item:3] and [item:1] and [item:3] again, then [item:2]."
    result = cited_item_ids(md)
    assert result == [3, 1, 2]


def test_cited_item_ids_empty_for_no_tags() -> None:
    """Empty list when markdown has no [item:N] tags."""
    result = cited_item_ids("No tags here whatsoever.")
    assert result == []


def test_cited_item_ids_single_tag() -> None:
    """Single tag returns a one-element list."""
    result = cited_item_ids("Read [item:42] for more.")
    assert result == [42]


# ---------------------------------------------------------------------------
# assemble_report citation recording tests
# ---------------------------------------------------------------------------


def test_citations_recorded_for_cited_items(
    db: sqlite3.Connection, sample_items: list[Item], sample_source: int, tmp_path: Path
) -> None:
    """After assemble_report, citations rows exist for each cited item."""
    item_a, item_b, _ = sample_items
    md = f"Analysis cites [item:{item_a.id}] and [item:{item_b.id}]."
    analyses = {"test-topic": _make_analysis(markdown=md)}

    report_id = assemble_report(
        analyses, "2025-01-01", db, _make_mock_client(), _make_settings(), reports_dir=tmp_path
    )

    rows = db.execute(
        "SELECT item_id, source_id FROM citations WHERE report_id = ?", (report_id,)
    ).fetchall()
    cited_ids = {r["item_id"] for r in rows}
    assert item_a.id in cited_ids
    assert item_b.id in cited_ids
    # Verify source_id is correctly resolved
    for row in rows:
        assert row["source_id"] == sample_source


def test_uncited_item_has_no_citations_row(
    db: sqlite3.Connection, sample_items: list[Item], tmp_path: Path
) -> None:
    """An item not referenced in any section produces no citation row."""
    item_a, _, item_c = sample_items
    # Only cite item_a; item_c is not mentioned
    md = f"Only [item:{item_a.id}] is cited."
    analyses = {"test-topic": _make_analysis(markdown=md)}

    report_id = assemble_report(
        analyses, "2025-01-02", db, _make_mock_client(), _make_settings(), reports_dir=tmp_path
    )

    row = db.execute(
        "SELECT id FROM citations WHERE report_id = ? AND item_id = ?", (report_id, item_c.id)
    ).fetchone()
    assert row is None


def test_nothing_significant_contributes_no_citations(
    db: sqlite3.Connection, sample_items: list[Item], tmp_path: Path
) -> None:
    """A nothing_significant topic does not produce citation rows even if ids appear in markdown."""
    item_a = sample_items[0]
    # The nothing_significant flag causes assemble_report to skip rendering the markdown
    analyses = {
        "ns-topic": _make_analysis(
            markdown=f"[item:{item_a.id}] is here but topic is nothing_significant",
            nothing_significant=True,
        )
    }

    report_id = assemble_report(
        analyses, "2025-01-03", db, _make_mock_client(), _make_settings(), reports_dir=tmp_path
    )

    count = db.execute(
        "SELECT COUNT(*) FROM citations WHERE report_id = ?", (report_id,)
    ).fetchone()[0]
    assert count == 0


def test_rerunning_assemble_does_not_duplicate_citations(
    db: sqlite3.Connection, sample_items: list[Item], tmp_path: Path
) -> None:
    """Re-running assemble_report for the same date does not duplicate citations rows."""
    item_a = sample_items[0]
    md = f"Cites [item:{item_a.id}]."
    analyses = {"test-topic": _make_analysis(markdown=md)}

    report_id = assemble_report(
        analyses, "2025-01-04", db, _make_mock_client(), _make_settings(), reports_dir=tmp_path
    )
    # Run again for the same date (UPSERT on reports, INSERT OR IGNORE on citations)
    assemble_report(
        analyses, "2025-01-04", db, _make_mock_client(), _make_settings(), reports_dir=tmp_path
    )

    count = db.execute(
        "SELECT COUNT(*) FROM citations WHERE report_id = ? AND item_id = ?",
        (report_id, item_a.id),
    ).fetchone()[0]
    assert count == 1


def test_nonexistent_item_id_skipped(db: sqlite3.Connection, tmp_path: Path) -> None:
    """Item ID that doesn't exist in the DB produces no citation row."""
    md = "References [item:99999] which is not in DB."
    analyses = {"test-topic": _make_analysis(markdown=md)}

    report_id = assemble_report(
        analyses, "2025-01-05", db, _make_mock_client(), _make_settings(), reports_dir=tmp_path
    )

    count = db.execute(
        "SELECT COUNT(*) FROM citations WHERE report_id = ?", (report_id,)
    ).fetchone()[0]
    assert count == 0


def test_citations_report_date_matches(
    db: sqlite3.Connection, sample_items: list[Item], tmp_path: Path
) -> None:
    """Citations rows carry the correct report_date."""
    item_a = sample_items[0]
    md = f"Cites [item:{item_a.id}]."
    analyses = {"test-topic": _make_analysis(markdown=md)}
    date = "2025-06-01"

    report_id = assemble_report(
        analyses, date, db, _make_mock_client(), _make_settings(), reports_dir=tmp_path
    )

    row = db.execute(
        "SELECT report_date FROM citations WHERE report_id = ? AND item_id = ?",
        (report_id, item_a.id),
    ).fetchone()
    assert row is not None
    assert row["report_date"] == date
