"""Telegram send: HTML digest (≤3,000 chars) + .md file attachment. See SPEC §10."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import sqlite3

from perpetual_analyst.store.models import Report

logger = logging.getLogger(__name__)


def send_report(report_id: int, conn: sqlite3.Connection) -> None:
    """Send digest HTML + full markdown file to Telegram.

    - Read report row from DB
    - Send digest_text as HTML message
    - Send full_markdown as document (brief-YYYY-MM-DD.md)
    - Mark delivered_at on success
    - Re-raise on Telegram error (caller handles retry)
    """
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if row is None:
        raise ValueError(f"Report {report_id} not found")

    report = Report.from_row(row)

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")

    # Import here so the module is importable even without telegram installed
    from telegram import Bot, InputFile  # type: ignore[import]

    async def _send() -> None:
        bot = Bot(token=token)
        filename = f"brief-{report.report_date}.md"
        doc_bytes = (report.full_markdown or "").encode("utf-8")
        await bot.send_document(
            chat_id=chat_id,
            document=InputFile(io.BytesIO(doc_bytes), filename=filename),
        )
        await bot.send_message(
            chat_id=chat_id,
            text=report.digest_text or "(no digest)",
            parse_mode="HTML",
        )

    asyncio.run(_send())

    conn.execute("UPDATE reports SET delivered_at = datetime('now') WHERE id = ?", (report_id,))
    conn.commit()


def retry_undelivered(conn: sqlite3.Connection) -> None:
    """Retry any reports not yet delivered that were created more than 1 hour ago."""
    rows = conn.execute(
        """SELECT * FROM reports
           WHERE delivered_at IS NULL
             AND created_at < datetime('now', '-1 hour')"""
    ).fetchall()

    for row in rows:
        report = Report.from_row(row)
        try:
            send_report(report.id, conn)
        except Exception:
            logger.exception("Failed to retry delivery for report %s", report.id)
