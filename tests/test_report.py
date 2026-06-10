"""Tests for report/render.py and report/assemble.py — Task 9."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from perpetual_analyst.analyst.schemas import TopicAnalysis
from perpetual_analyst.report.assemble import assemble_report
from perpetual_analyst.report.render import render_citations
from perpetual_analyst.store.db import init_db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = init_db(":memory:")
    conn.execute("INSERT OR REPLACE INTO users (id, telegram_chat_id) VALUES (1, 'test-chat-id')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def db_with_item(db: sqlite3.Connection) -> sqlite3.Connection:
    """DB with a known item (id=1) that has title and URL."""
    db.execute("INSERT INTO sources (type, name) VALUES ('inbox', 'Test')")
    db.execute(
        "INSERT INTO items (id, source_id, content_hash, title, url, raw_text)"
        " VALUES (1, 1, 'hash1', 'Test Article', 'https://example.com/1', 'text')"
    )
    db.commit()
    return db


@pytest.fixture
def db_with_item_no_url(db: sqlite3.Connection) -> sqlite3.Connection:
    """DB with a known item (id=2) that has title but no URL."""
    db.execute("INSERT INTO sources (type, name) VALUES ('inbox', 'Test')")
    db.execute(
        "INSERT INTO items (id, source_id, content_hash, title, url, raw_text)"
        " VALUES (2, 1, 'hash2', 'No URL Article', NULL, 'text')"
    )
    db.commit()
    return db


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
    nothing_significant: bool = False, markdown: str = "## Topic\n\nContent"
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
# render_citations tests
# ---------------------------------------------------------------------------


def test_render_citations_replaces_tags(db_with_item: sqlite3.Connection) -> None:
    """[item:1] tag replaced with [^1] inline and footnote appended."""
    md = "See analysis [item:1] for details."
    result = render_citations(md, db_with_item)
    assert "[^1]" in result
    assert "[item:1]" not in result
    assert "---" in result
    assert "[^1]:" in result
    assert "Test Article" in result
    assert "https://example.com/1" in result


def test_render_citations_no_tags(db: sqlite3.Connection) -> None:
    """Markdown with no [item:N] tags returned unchanged."""
    md = "No citations here at all."
    result = render_citations(md, db)
    assert result == md


def test_render_citations_missing_item_fallback(db: sqlite3.Connection) -> None:
    """Unknown item ID falls back to (item N)."""
    md = "See [item:9999] for proof."
    result = render_citations(md, db)
    assert "[^9999]" in result
    assert "(item 9999)" in result


def test_render_citations_no_url_item(db_with_item_no_url: sqlite3.Connection) -> None:
    """Item without URL produces footnote without a hyperlink."""
    md = "Check [item:2] again."
    result = render_citations(md, db_with_item_no_url)
    assert "[^2]" in result
    assert "No URL Article" in result
    # Should NOT contain a markdown link format [title](url)
    assert "](http" not in result


# ---------------------------------------------------------------------------
# assemble_report tests
# ---------------------------------------------------------------------------


def test_assemble_report_writes_to_db(db: sqlite3.Connection, tmp_path: Path) -> None:
    """Report row created with the correct date."""
    client = _make_mock_client()
    settings = _make_settings()
    analyses = {"topic-a": _make_analysis()}

    report_id = assemble_report(analyses, "2024-01-15", db, client, settings, reports_dir=tmp_path)

    row = db.execute("SELECT * FROM reports WHERE report_date = '2024-01-15'").fetchone()
    assert row is not None
    assert row["report_date"] == "2024-01-15"
    assert report_id == row["id"]


def test_assemble_report_writes_markdown_file(db: sqlite3.Connection, tmp_path: Path) -> None:
    """Markdown file written to reports_dir/brief-{date}.md."""
    client = _make_mock_client()
    settings = _make_settings()
    analyses = {"topic-a": _make_analysis()}

    assemble_report(analyses, "2024-01-15", db, client, settings, reports_dir=tmp_path)

    md_file = tmp_path / "brief-2024-01-15.md"
    assert md_file.exists()
    content = md_file.read_text(encoding="utf-8")
    assert "2024-01-15" in content


def test_assemble_report_nothing_significant(db: sqlite3.Connection, tmp_path: Path) -> None:
    """nothing_significant topic produces 'Nothing significant today.' section."""
    client = _make_mock_client()
    settings = _make_settings()
    analyses = {"topic-a": _make_analysis(nothing_significant=True)}

    assemble_report(analyses, "2024-01-15", db, client, settings, reports_dir=tmp_path)

    row = db.execute(
        "SELECT full_markdown FROM reports WHERE report_date = '2024-01-15'"
    ).fetchone()
    assert "Nothing significant today." in row["full_markdown"]


def test_assemble_report_returns_report_id(db: sqlite3.Connection, tmp_path: Path) -> None:
    """assemble_report returns an integer row ID."""
    client = _make_mock_client()
    settings = _make_settings()
    analyses = {"topic-a": _make_analysis()}

    report_id = assemble_report(analyses, "2024-01-15", db, client, settings, reports_dir=tmp_path)

    assert isinstance(report_id, int)
    assert report_id > 0
