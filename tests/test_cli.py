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
    conn.execute("INSERT OR REPLACE INTO users (id, telegram_chat_id) VALUES (1, 'test-chat-id')")
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


def test_topic_add_invalid_slug(tmp_db):
    result = runner.invoke(app, ["topic", "add", "My Topic!", "--name", "Bad Slug"])
    assert result.exit_code == 1
    assert "Invalid slug" in result.output


def test_topic_add_path_traversal_slug(tmp_db):
    result = runner.invoke(app, ["topic", "add", "../etc", "--name", "Traversal"])
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


def test_source_add_sets_probation(tmp_db):
    """source add starts the new source in probation with a non-null probation_until."""
    runner.invoke(app, ["topic", "add", "ai-safety", "--name", "AI Safety"])
    runner.invoke(
        app,
        ["source", "add", "--topic", "ai-safety", "--type", "rss", "--url", "https://ex.com/rss"],
    )
    conn = init_db(tmp_db)
    row = conn.execute("SELECT status, probation_until FROM sources WHERE type = 'rss'").fetchone()
    assert row["status"] == "probation"
    assert row["probation_until"] is not None


def test_source_add_echo_mentions_probation(tmp_db):
    """The success echo from source add mentions 'probation'."""
    runner.invoke(app, ["topic", "add", "ai-safety", "--name", "AI Safety"])
    result = runner.invoke(
        app,
        ["source", "add", "--topic", "ai-safety", "--type", "rss", "--url", "https://ex.com/rss"],
    )
    assert result.exit_code == 0
    assert "probation" in result.output


def test_source_add_unknown_topic(tmp_db):
    result = runner.invoke(app, ["source", "add", "--topic", "no-such", "--type", "rss"])
    assert result.exit_code == 1


def test_source_candidates_empty(tmp_db):
    """source candidates prints 'No candidates.' when source_candidates table is empty."""
    result = runner.invoke(app, ["source", "candidates"])
    assert result.exit_code == 0
    assert "No candidates" in result.output


def test_source_candidates_lists_row(tmp_db):
    """source candidates prints a seeded source_candidates row."""
    runner.invoke(app, ["topic", "add", "ai-safety", "--name", "AI Safety"])
    conn = init_db(tmp_db)
    topic_row = conn.execute("SELECT id FROM topics WHERE slug = 'ai-safety'").fetchone()
    conn.execute(
        "INSERT INTO source_candidates (topic_id, url, domain, rationale, status)"
        " VALUES (?, 'https://example.com', 'example.com', 'Great source for safety news',"
        " 'pending')",
        (topic_row["id"],),
    )
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["source", "candidates"])
    assert result.exit_code == 0
    assert "example.com" in result.output
    assert "Great source" in result.output


def test_source_candidates_filter_by_topic(tmp_db):
    """source candidates --topic filters to the given topic's candidates only."""
    runner.invoke(app, ["topic", "add", "ai-safety", "--name", "AI Safety"])
    runner.invoke(app, ["topic", "add", "compute", "--name", "Compute"])
    conn = init_db(tmp_db)
    t1 = conn.execute("SELECT id FROM topics WHERE slug = 'ai-safety'").fetchone()
    t2 = conn.execute("SELECT id FROM topics WHERE slug = 'compute'").fetchone()
    conn.execute(
        "INSERT INTO source_candidates (topic_id, url, domain, rationale, status)"
        " VALUES (?, 'https://safety.example.com', 'safety.example.com', 'safety news', 'pending')",
        (t1["id"],),
    )
    conn.execute(
        "INSERT INTO source_candidates (topic_id, url, domain, rationale, status)"
        " VALUES (?, 'https://compute.example.com', 'compute.example.com', 'compute news',"
        " 'pending')",
        (t2["id"],),
    )
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["source", "candidates", "--topic", "ai-safety"])
    assert result.exit_code == 0
    assert "safety.example.com" in result.output
    assert "compute.example.com" not in result.output


def test_source_candidates_unknown_topic(tmp_db):
    """source candidates --topic with unknown slug exits with code 1."""
    result = runner.invoke(app, ["source", "candidates", "--topic", "no-such"])
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


def test_run_dry_run_no_items(tmp_db, monkeypatch):
    from unittest.mock import MagicMock

    import perpetual_analyst.cli as cli_mod

    # make_client must never be called for dry-run
    monkeypatch.setattr(cli_mod, "_db", cli_mod._db)
    make_client_mock = MagicMock(side_effect=AssertionError("make_client called in dry-run"))
    monkeypatch.setattr("perpetual_analyst.analyst.agent.make_client", make_client_mock)

    runner.invoke(app, ["topic", "add", "ai-safety", "--name", "AI Safety"])
    result = runner.invoke(app, ["run", "--topic", "ai-safety", "--dry-run"])
    assert result.exit_code == 0, result.output
    # dry-run prints assembled prompt messages
    assert "[SYSTEM]" in result.output
    assert "0 item(s)" in result.output
    make_client_mock.assert_not_called()


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
