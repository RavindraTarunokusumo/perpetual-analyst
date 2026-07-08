"""Tests for delivery/telegram.py — Task 10."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from perpetual_analyst.delivery.telegram import retry_undelivered, send_report
from perpetual_analyst.store.db import init_db


@contextmanager
def _mock_telegram(bot: AsyncMock):
    """Context manager that injects a mock telegram module and restores sys.modules after."""
    mock_mod = MagicMock()
    mock_mod.Bot = MagicMock(return_value=bot)
    mock_mod.InputFile = MagicMock(side_effect=lambda *a, **kw: MagicMock())
    saved = {k: sys.modules[k] for k in list(sys.modules) if k.startswith("telegram")}
    sys.modules["telegram"] = mock_mod
    try:
        yield mock_mod
    finally:
        for k in list(sys.modules):
            if k.startswith("telegram"):
                del sys.modules[k]
        sys.modules.update(saved)


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


# ---------------------------------------------------------------------------
# Happy-path and security tests
# ---------------------------------------------------------------------------


def test_send_report_happy_path(db: sqlite3.Connection, monkeypatch) -> None:
    """send_report sends message + document and marks delivered_at."""
    report_id = _insert_report(db, digest_text="<b>Test</b>", full_markdown="# Test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "fake-chat-id")

    mock_bot = AsyncMock()
    with _mock_telegram(mock_bot):
        send_report(report_id, db)

    mock_bot.send_message.assert_awaited_once()
    mock_bot.send_document.assert_awaited_once()

    row = db.execute("SELECT delivered_at FROM reports WHERE id = ?", (report_id,)).fetchone()
    assert row["delivered_at"] is not None


def test_send_report_document_sent_before_message(db: sqlite3.Connection, monkeypatch) -> None:
    """Document must be sent before message so a message-send failure leaves no duplicate digest."""
    report_id = _insert_report(db, digest_text="<b>Test</b>", full_markdown="# Test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "fake-chat-id")

    call_order: list[str] = []

    mock_bot = AsyncMock()
    mock_bot.send_document = AsyncMock(side_effect=lambda **kw: call_order.append("document"))
    mock_bot.send_message = AsyncMock(side_effect=lambda **kw: call_order.append("message"))

    with _mock_telegram(mock_bot):
        send_report(report_id, db)

    assert call_order == ["document", "message"], f"Expected doc-first order, got {call_order}"


def test_send_report_error_does_not_log_token(
    db: sqlite3.Connection, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    """On Telegram failure, the error logged by retry_undelivered must not contain the token."""
    import logging

    _insert_report(db, created_offset="2 hours")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "super-secret-token-xyz")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "fake-chat-id")

    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock(side_effect=RuntimeError("network error"))
    with _mock_telegram(mock_bot), caplog.at_level(logging.ERROR):
        retry_undelivered(db)

    assert "super-secret-token-xyz" not in caplog.text
