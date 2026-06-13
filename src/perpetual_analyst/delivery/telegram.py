"""Telegram send: HTML digest (<=3,000 chars) + .md attachment. Send-only V1. See SPEC §10."""

from __future__ import annotations

import asyncio
import html
import io
import os
import re
import sqlite3

from telegram import Bot

from perpetual_analyst.store.models import Report

DIGEST_CHAR_LIMIT = 3000

_ALLOWED_TAG_RE = re.compile(r"</?([bi])>")


def _escape_preserving_tags(text: str) -> str:
    """HTML-escape stray <, >, & for Telegram HTML, keeping <b>/<i> tags intact."""
    out: list[str] = []
    pos = 0
    for match in _ALLOWED_TAG_RE.finditer(text):
        out.append(html.escape(text[pos : match.start()], quote=False))
        out.append(match.group(0))
        pos = match.end()
    out.append(html.escape(text[pos:], quote=False))
    return "".join(out)


def _close_open_tags(text: str) -> str:
    """Close any unclosed <b>/<i> in order (run after escaping, so only real tags remain)."""
    stack: list[str] = []
    for match in _ALLOWED_TAG_RE.finditer(text):
        name = match.group(1)
        if match.group(0).startswith("</"):
            if stack and stack[-1] == name:
                stack.pop()
        else:
            stack.append(name)
    for name in reversed(stack):
        text += f"</{name}>"
    return text


def _truncate_at_paragraph(text: str, limit: int = DIGEST_CHAR_LIMIT) -> str:
    """Truncate at a paragraph boundary, escape for Telegram HTML, close open tags."""
    if len(text) > limit:
        cut = text[:limit]
        boundary = cut.rfind("\n\n")
        if boundary > 0:
            cut = cut[:boundary]
        text = cut
    return _close_open_tags(_escape_preserving_tags(text))


async def _send(token: str, chat_id: str, digest: str, report: Report) -> None:
    bot = Bot(token=token)
    async with bot:
        await bot.send_message(chat_id=chat_id, text=digest, parse_mode="HTML")
        await bot.send_document(
            chat_id=chat_id,
            document=io.BytesIO((report.full_markdown or "").encode("utf-8")),
            filename=f"brief-{report.report_date}.md",
        )


def send_report(report: Report, conn: sqlite3.Connection) -> bool:
    """Deliver one report; stamps delivered_at on success. Env-gated, never raises."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[telegram] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set - skipping delivery")
        return False

    digest = _truncate_at_paragraph(report.digest_text or "")
    try:
        asyncio.run(_send(token, chat_id, digest, report))
    except Exception as exc:
        # exception text could embed the token (e.g. request URLs) - print type only
        print(f"[telegram] send failed for {report.report_date}: {type(exc).__name__}")
        return False

    conn.execute("UPDATE reports SET delivered_at = datetime('now') WHERE id = ?", (report.id,))
    conn.commit()
    return True


def retry_undelivered(conn: sqlite3.Connection) -> int:
    """Send every report with delivered_at IS NULL; returns count delivered."""
    rows = conn.execute(
        "SELECT * FROM reports WHERE delivered_at IS NULL ORDER BY report_date"
    ).fetchall()
    return sum(1 for row in rows if send_report(Report.from_row(row), conn))
