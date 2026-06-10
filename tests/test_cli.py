"""Tests for cli.py using typer's CliRunner + an isolated SQLite DB per test."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from perpetual_analyst.cli import app
from perpetual_analyst.store.db import init_db

runner = CliRunner()


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("ANALYST_DB_PATH", db_path)
    conn = init_db(db_path)
    conn.execute("INSERT INTO users (id, telegram_chat_id) VALUES (1, 'test-chat-id')")
    conn.commit()
    conn.close()
    return db_path


# ── topic ──────────────────────────────────────────────────────────────────────


def test_topic_add(tmp_db):
    result = runner.invoke(app, ["topic", "add", "ai-safety", "--name", "AI Safety"])
    assert result.exit_code == 0, result.output
    assert "Added topic 'ai-safety'" in result.output


def test_topic_add_with_brief(tmp_db):
    result = runner.invoke(
        app,
        [
            "topic",
            "add",
            "compute",
            "--name",
            "Compute Trends",
            "--brief",
            "Track GPU and TPU scaling",
        ],
    )
    assert result.exit_code == 0
    assert "compute" in result.output


def test_topic_add_duplicate(tmp_db):
    runner.invoke(app, ["topic", "add", "ai-safety", "--name", "AI Safety"])
    result = runner.invoke(app, ["topic", "add", "ai-safety", "--name", "AI Safety Dupe"])
    assert result.exit_code == 1


def test_topic_list_empty(tmp_db):
    result = runner.invoke(app, ["topic", "list"])
    assert result.exit_code == 0
    assert "No topics" in result.output


def test_topic_list_shows_added(tmp_db):
    runner.invoke(
        app, ["topic", "add", "ai-safety", "--name", "AI Safety", "--brief", "Track safety"]
    )
    result = runner.invoke(app, ["topic", "list"])
    assert result.exit_code == 0
    assert "ai-safety" in result.output
    assert "active" in result.output


# ── source ─────────────────────────────────────────────────────────────────────


def test_source_add(tmp_db):
    runner.invoke(app, ["topic", "add", "ai-safety", "--name", "AI Safety"])
    result = runner.invoke(
        app,
        [
            "source",
            "add",
            "--topic",
            "ai-safety",
            "--type",
            "rss",
            "--url",
            "https://example.com/feed",
        ],
    )
    assert result.exit_code == 0
    assert "Added source" in result.output


def test_source_add_unknown_topic(tmp_db):
    result = runner.invoke(app, ["source", "add", "--topic", "no-such", "--type", "rss"])
    assert result.exit_code == 1


def test_source_list(tmp_db):
    runner.invoke(app, ["topic", "add", "ai-safety", "--name", "AI Safety"])
    runner.invoke(
        app,
        [
            "source",
            "add",
            "--topic",
            "ai-safety",
            "--type",
            "rss",
            "--url",
            "https://example.com/feed",
        ],
    )
    result = runner.invoke(app, ["source", "list", "--topic", "ai-safety"])
    assert result.exit_code == 0
    assert "rss" in result.output


# ── run ────────────────────────────────────────────────────────────────────────


def test_run_no_active_topics(tmp_db):
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 0
    assert "No active topics" in result.output


def test_run_unknown_topic(tmp_db):
    result = runner.invoke(app, ["run", "--topic", "no-such"])
    assert result.exit_code == 1


def test_run_dry_run_no_items(tmp_db):
    runner.invoke(app, ["topic", "add", "ai-safety", "--name", "AI Safety"])
    result = runner.invoke(app, ["run", "--topic", "ai-safety", "--dry-run"])
    assert result.exit_code == 0, result.output
    # dry-run prints assembled prompt messages
    assert "[SYSTEM]" in result.output
    assert "0 item(s)" in result.output


# ── report ─────────────────────────────────────────────────────────────────────


def test_report_show_no_report(tmp_db):
    result = runner.invoke(app, ["report", "show"])
    assert result.exit_code == 1


def test_report_show_by_date(tmp_db, monkeypatch):
    from perpetual_analyst.store.db import init_db as _init

    conn = _init(tmp_db)
    conn.execute(
        "INSERT INTO reports (report_date, full_markdown) VALUES ('2026-01-01', '# Day 1 Report')"
    )
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["report", "show", "--date", "2026-01-01"])
    assert result.exit_code == 0
    assert "Day 1 Report" in result.output
