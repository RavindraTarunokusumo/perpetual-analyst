"""Tests for daily_run.py — Task 10."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from perpetual_analyst.analyst.schemas import TopicAnalysis
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


def _make_topic_analysis(nothing_significant: bool = False) -> TopicAnalysis:
    return TopicAnalysis(
        report_section_markdown="" if nothing_significant else "## Topic\n\nContent",
        new_observations=[],
        thesis_updates=[],
        dossier_edits=None,
        open_questions=[],
        watch_next=[],
        nothing_significant=nothing_significant,
    )


def _insert_topic(conn: sqlite3.Connection, slug: str, active: int = 1) -> int:
    cur = conn.execute(
        "INSERT INTO topics (user_id, slug, name, active) VALUES (1, ?, ?, ?)",
        (slug, slug.replace("-", " ").title(), active),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# daily_run.main tests
# ---------------------------------------------------------------------------


def test_main_dry_run_no_topics(db: sqlite3.Connection) -> None:
    """dry_run=True with no active topics exits cleanly without errors."""
    from perpetual_analyst.daily_run import main

    with (
        patch("perpetual_analyst.daily_run.init_db", return_value=db),
        patch("perpetual_analyst.daily_run.load_settings", return_value=MagicMock()),
        patch("perpetual_analyst.daily_run.retry_undelivered"),
        patch("perpetual_analyst.daily_run.run_topic") as mock_run,
        patch("perpetual_analyst.daily_run.assemble_report") as mock_assemble,
        patch("perpetual_analyst.daily_run.send_report") as mock_send,
    ):
        main(dry_run=True)

        mock_run.assert_not_called()
        mock_assemble.assert_not_called()
        mock_send.assert_not_called()


def test_main_isolates_topic_failures(db: sqlite3.Connection) -> None:
    """If one topic's run_topic raises, others still run."""
    _insert_topic(db, "topic-a")
    _insert_topic(db, "topic-b")

    from perpetual_analyst.daily_run import main

    good_result = _make_topic_analysis()

    def run_topic_side_effect(topic, items, conn, client, settings, dry_run=False):
        if topic.slug == "topic-a":
            raise RuntimeError("topic-a exploded")
        return good_result

    with (
        patch("perpetual_analyst.daily_run.init_db", return_value=db),
        patch("perpetual_analyst.daily_run.load_settings", return_value=MagicMock()),
        patch("perpetual_analyst.daily_run.retry_undelivered"),
        patch("perpetual_analyst.daily_run.make_client", return_value=MagicMock()),
        patch("perpetual_analyst.daily_run.scan_inbox", return_value=[]),
        patch("perpetual_analyst.daily_run.run_topic", side_effect=run_topic_side_effect),
        patch("perpetual_analyst.daily_run.assemble_report", return_value=1),
        patch("perpetual_analyst.daily_run.send_report"),
    ):
        # Should not raise even though topic-a fails
        main(dry_run=False)


def test_main_skips_delivery_on_dry_run(db: sqlite3.Connection) -> None:
    """dry_run=True means assemble_report and send_report are never called."""
    _insert_topic(db, "my-topic")

    from perpetual_analyst.daily_run import main

    with (
        patch("perpetual_analyst.daily_run.init_db", return_value=db),
        patch("perpetual_analyst.daily_run.load_settings", return_value=MagicMock()),
        patch("perpetual_analyst.daily_run.retry_undelivered"),
        patch("perpetual_analyst.daily_run.scan_inbox", return_value=[]),
        patch("perpetual_analyst.daily_run.run_topic", return_value=None),
        patch("perpetual_analyst.daily_run.assemble_report") as mock_assemble,
        patch("perpetual_analyst.daily_run.send_report") as mock_send,
    ):
        main(dry_run=True)

        mock_assemble.assert_not_called()
        mock_send.assert_not_called()
