"""Tests for delivery/telegram.py — Task 10."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from perpetual_analyst.delivery.telegram import retry_undelivered, send_report
from perpetual_analyst.store.db import init_db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = init_db(":memory:")
    conn.execute("INSERT INTO users (id, telegram_chat_id) VALUES (1, 'test-chat-id')")
    conn.commit()
    yield conn
    conn.close()


def _insert_report(
    conn: sqlite3.Connection,
    *,
    report_date: str = "2024-01-15",
    digest_text: str = "<b>Summary</b>",
    full_markdown: str = "# Report\n\nContent",
    delivered_at: str | None = None,
    created_offset: str = "0 hours",
) -> int:
    """Insert a test report row; returns its id."""
    cur = conn.execute(
        """INSERT INTO reports (report_date, digest_text, full_markdown, delivered_at, created_at)
           VALUES (?, ?, ?, ?, datetime('now', ?))""",
        (report_date, digest_text, full_markdown, delivered_at, f"-{created_offset}"),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# send_report tests
# ---------------------------------------------------------------------------


def test_send_report_raises_on_missing_env(db: sqlite3.Connection, monkeypatch) -> None:
    """RuntimeError raised when TELEGRAM_BOT_TOKEN is not set."""
    report_id = _insert_report(db)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        send_report(report_id, db)

    # Error message must NOT contain the token value
    assert "TELEGRAM_BOT_TOKEN" in str(exc_info.value) or "TELEGRAM_CHAT_ID" in str(exc_info.value)


def test_send_report_raises_on_missing_report(db: sqlite3.Connection, monkeypatch) -> None:
    """ValueError raised when report_id does not exist."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "fake-chat-id")

    with pytest.raises(ValueError, match="Report 9999 not found"):
        send_report(9999, db)


# ---------------------------------------------------------------------------
# retry_undelivered tests
# ---------------------------------------------------------------------------


def test_retry_undelivered_skips_delivered(db: sqlite3.Connection, monkeypatch) -> None:
    """Reports that are already delivered are not retried."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "fake-chat-id")

    # Insert a report that IS already delivered (created 2h ago)
    _insert_report(
        db,
        report_date="2024-01-13",
        delivered_at="2024-01-13 10:00:00",
        created_offset="2 hours",
    )

    with patch("perpetual_analyst.delivery.telegram.send_report") as mock_send:
        retry_undelivered(db)
        mock_send.assert_not_called()


def test_retry_undelivered_skips_recent(db: sqlite3.Connection, monkeypatch) -> None:
    """Reports created less than 1 hour ago are not retried even if undelivered."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "fake-chat-id")

    # Insert a report created 10 minutes ago, not yet delivered
    _insert_report(
        db,
        report_date="2024-01-14",
        delivered_at=None,
        created_offset="10 minutes",
    )

    with patch("perpetual_analyst.delivery.telegram.send_report") as mock_send:
        retry_undelivered(db)
        mock_send.assert_not_called()
