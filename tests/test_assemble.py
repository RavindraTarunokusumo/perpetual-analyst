from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from perpetual_analyst.analyst.schemas import DigestOutput, TopicAnalysis
from perpetual_analyst.report.assemble import assemble_report, persist_report


def _analysis(section="## What's new\nThings happened.", nothing=False, **kw):
    return TopicAnalysis(
        report_section_markdown=section,
        nothing_significant=nothing,
        **kw,
    )


def _digest_client(executive_summary="Exec.", digest_text="Digest."):
    parsed = DigestOutput(executive_summary=executive_summary, digest_text=digest_text)
    message = MagicMock()
    message.parsed = parsed
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.beta.chat.completions.parse.return_value = response
    return client


def test_assemble_merges_sections_and_digest(db, sample_topic, settings):
    digest_text, full = assemble_report(
        [(sample_topic, _analysis(open_questions=["Q1?"], watch_next=["W1"]))],
        db,
        _digest_client(),
        settings,
        "2026-06-12",
    )
    assert digest_text == "Digest."
    assert "# Daily Intelligence Brief — 2026-06-12" in full
    assert "## Executive summary" in full and "Exec." in full
    assert f"## Topic: {sample_topic.name}" in full
    assert "Things happened." in full
    assert "## Open questions" in full and "Q1?" in full
    assert "## Things to watch next" in full and "W1" in full


def test_nothing_significant_topic_gets_one_line(db, sample_topic, settings):
    _, full = assemble_report(
        [(sample_topic, _analysis(section="", nothing=True))],
        db,
        _digest_client(),
        settings,
        "2026-06-12",
    )
    assert f"*{sample_topic.name}: nothing significant today.*" in full
    assert "## What's new" not in full


def test_empty_optional_sections_omitted(db, sample_topic, settings):
    _, full = assemble_report(
        [(sample_topic, _analysis())], db, _digest_client(), settings, "2026-06-12"
    )
    assert "## Open questions" not in full
    assert "## Things to watch next" not in full


def test_digest_failure_falls_back(db, sample_topic, settings):
    client = MagicMock()
    client.beta.chat.completions.parse.side_effect = RuntimeError("api down")
    digest_text, full = assemble_report(
        [(sample_topic, _analysis())], db, client, settings, "2026-06-12"
    )
    assert "Things happened." in digest_text  # mechanical fallback
    assert "## Executive summary" not in full


def test_citations_rendered_in_full_report(db, sample_topic, sample_source, settings):
    cur = db.execute(
        "INSERT INTO items (source_id, content_hash, title, url)"
        " VALUES (?, 'h1', 'Cited Post', 'https://example.com/c')",
        (sample_source,),
    )
    db.commit()
    analysis = _analysis(section=f"Confirmed by [item:{cur.lastrowid}].")
    _, full = assemble_report(
        [(sample_topic, analysis)], db, _digest_client(), settings, "2026-06-12"
    )
    assert "[^1]" in full and "Cited Post" in full


def test_todays_thesis_updates_appended(db, sample_topic, settings):
    db.execute(
        "INSERT INTO theses (topic_id, statement, confidence, status)"
        " VALUES (?, 'T1 statement', 0.7, 'active')",
        (sample_topic.id,),
    )
    thesis_id = db.execute("SELECT id FROM theses").fetchone()["id"]
    db.execute(
        "INSERT INTO thesis_updates (thesis_id, change, confidence_before, confidence_after)"
        " VALUES (?, 'Raised on new signal.', 0.5, 0.7)",
        (thesis_id,),
    )
    db.commit()
    _, full = assemble_report(
        [(sample_topic, _analysis())],
        db,
        _digest_client(),
        settings,
        db.execute("SELECT date('now')").fetchone()[0],
    )
    assert "### Thesis updates" in full
    assert "0.50 → 0.70" in full


def test_persist_report_writes_row_and_file(db, tmp_path):
    report_id = persist_report("2026-06-12", "digest", "# Full", db, reports_dir=str(tmp_path))
    row = db.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    assert row["report_date"] == "2026-06-12"
    assert row["delivered_at"] is None
    assert (tmp_path / "brief-2026-06-12.md").read_text(encoding="utf-8") == "# Full"


def test_persist_duplicate_date_raises(db, tmp_path):
    persist_report("2026-06-12", "d", "f", db, reports_dir=str(tmp_path))
    with pytest.raises(Exception):
        persist_report("2026-06-12", "d", "f", db, reports_dir=str(tmp_path))
