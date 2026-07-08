"""Tests for report/assemble.py."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from perpetual_analyst.analyst.schemas import NarrativeUpdate
from perpetual_analyst.report.assemble import assemble_report
from perpetual_analyst.store.db import init_db


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = init_db(":memory:")
    conn.execute("INSERT OR REPLACE INTO users (id, telegram_chat_id) VALUES (1, 'test-chat-id')")
    conn.commit()
    yield conn
    conn.close()


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


def _make_briefing(
    nothing_significant: bool = False, markdown: str = "## Topic\n\nContent from briefing."
) -> NarrativeUpdate:
    return NarrativeUpdate(
        narrative_summary="Summary",
        change_summary="No change",
        briefing_markdown="" if nothing_significant else markdown,
        nothing_significant=nothing_significant,
    )


def test_assemble_report_writes_to_db(db: sqlite3.Connection, tmp_path: Path) -> None:
    client = _make_mock_client()
    settings = _make_settings()
    briefings = {"topic-a": _make_briefing()}

    report_id = assemble_report(briefings, "2024-01-15", db, client, settings, reports_dir=tmp_path)

    row = db.execute("SELECT * FROM reports WHERE report_date = '2024-01-15'").fetchone()
    assert row is not None
    assert row["report_date"] == "2024-01-15"
    assert report_id == row["id"]


def test_assemble_report_writes_markdown_file(db: sqlite3.Connection, tmp_path: Path) -> None:
    client = _make_mock_client()
    settings = _make_settings()
    briefings = {"topic-a": _make_briefing()}

    assemble_report(briefings, "2024-01-15", db, client, settings, reports_dir=tmp_path)

    md_file = tmp_path / "brief-2024-01-15.md"
    assert md_file.exists()
    content = md_file.read_text(encoding="utf-8")
    assert "2024-01-15" in content
    assert "Content from briefing." in content


def test_assemble_report_nothing_significant(db: sqlite3.Connection, tmp_path: Path) -> None:
    client = _make_mock_client()
    settings = _make_settings()
    briefings = {"topic-a": _make_briefing(nothing_significant=True)}

    assemble_report(briefings, "2024-01-15", db, client, settings, reports_dir=tmp_path)

    row = db.execute(
        "SELECT full_markdown FROM reports WHERE report_date = '2024-01-15'"
    ).fetchone()
    assert "Nothing significant." in row["full_markdown"]


def test_assemble_report_returns_report_id(db: sqlite3.Connection, tmp_path: Path) -> None:
    client = _make_mock_client()
    settings = _make_settings()
    briefings = {"topic-a": _make_briefing()}

    report_id = assemble_report(briefings, "2024-01-15", db, client, settings, reports_dir=tmp_path)

    assert isinstance(report_id, int)
    assert report_id > 0
