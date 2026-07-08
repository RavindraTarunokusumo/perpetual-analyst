"""Tests for daily_run.py."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from perpetual_analyst.analyst.schemas import NarrativeUpdate
from perpetual_analyst.store.db import init_db


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = init_db(":memory:")
    conn.execute("INSERT OR REPLACE INTO users (id, telegram_chat_id) VALUES (1, 'test-chat-id')")
    conn.commit()
    yield conn
    conn.close()


def _make_narrative_update(nothing_significant: bool = False) -> NarrativeUpdate:
    return NarrativeUpdate(
        narrative_summary="Summary",
        change_summary="No change",
        briefing_markdown="" if nothing_significant else "## Topic\n\nContent",
        nothing_significant=nothing_significant,
    )


def _insert_topic(conn: sqlite3.Connection, slug: str, active: int = 1) -> int:
    cur = conn.execute(
        "INSERT INTO topics (user_id, slug, name, active) VALUES (1, ?, ?, ?)",
        (slug, slug.replace("-", " ").title(), active),
    )
    conn.commit()
    return cur.lastrowid


def test_main_dry_run_no_topics(db: sqlite3.Connection) -> None:
    from perpetual_analyst.daily_run import main

    with (
        patch("perpetual_analyst.daily_run.init_db", return_value=db),
        patch("perpetual_analyst.daily_run.load_settings", return_value=MagicMock()),
        patch("perpetual_analyst.daily_run.retry_undelivered"),
        patch("perpetual_analyst.analyst.synthesis.run_daily_for_topic") as mock_synthesis,
        patch("perpetual_analyst.daily_run.assemble_report") as mock_assemble,
        patch("perpetual_analyst.daily_run.send_report") as mock_send,
    ):
        main(dry_run=True)

        mock_synthesis.assert_not_called()
        mock_assemble.assert_not_called()
        mock_send.assert_not_called()


def test_main_isolates_topic_failures(db: sqlite3.Connection) -> None:
    _insert_topic(db, "topic-a")
    _insert_topic(db, "topic-b")

    from perpetual_analyst.daily_run import main

    good_bundle = _make_narrative_update()

    def synthesis_side_effect(slug, name, brief, titles, k=8):
        if slug == "topic-a":
            raise RuntimeError("topic-a exploded")
        return good_bundle, "ok", 100

    with (
        patch("perpetual_analyst.daily_run.init_db", return_value=db),
        patch("perpetual_analyst.daily_run.load_settings", return_value=MagicMock()),
        patch("perpetual_analyst.daily_run.retry_undelivered"),
        patch("perpetual_analyst.daily_run.make_client", return_value=MagicMock()),
        patch("perpetual_analyst.daily_run.scan_inbox", return_value=[]),
        patch("perpetual_analyst.daily_run._ingest_to_corpus", return_value=0),
        patch(
            "perpetual_analyst.analyst.synthesis.run_daily_for_topic",
            side_effect=synthesis_side_effect,
        ),
        patch("perpetual_analyst.daily_run.assemble_report", return_value=1),
        patch("perpetual_analyst.daily_run.send_report"),
    ):
        main(dry_run=False)


def test_main_skips_delivery_on_dry_run(db: sqlite3.Connection) -> None:
    _insert_topic(db, "my-topic")

    from perpetual_analyst.daily_run import main

    with (
        patch("perpetual_analyst.daily_run.init_db", return_value=db),
        patch("perpetual_analyst.daily_run.load_settings", return_value=MagicMock()),
        patch("perpetual_analyst.daily_run.retry_undelivered"),
        patch("perpetual_analyst.daily_run.scan_inbox", return_value=[]),
        patch("perpetual_analyst.analyst.synthesis.run_daily_for_topic") as mock_synthesis,
        patch("perpetual_analyst.daily_run.assemble_report") as mock_assemble,
        patch("perpetual_analyst.daily_run.send_report") as mock_send,
    ):
        main(dry_run=True)

        mock_synthesis.assert_not_called()
        mock_assemble.assert_not_called()
        mock_send.assert_not_called()
