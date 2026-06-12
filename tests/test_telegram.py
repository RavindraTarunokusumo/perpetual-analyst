from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from perpetual_analyst.delivery import telegram
from perpetual_analyst.store.models import Report


def _report(db, report_date="2026-06-12", digest="hello <b>world</b>"):
    cur = db.execute(
        "INSERT INTO reports (report_date, digest_text, full_markdown) VALUES (?, ?, ?)",
        (report_date, digest, "# Full report"),
    )
    db.commit()
    row = db.execute("SELECT * FROM reports WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Report.from_row(row)


@pytest.fixture
def tg_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")


@pytest.fixture
def sent(monkeypatch):
    calls = AsyncMock()
    monkeypatch.setattr(telegram, "_send", calls)
    return calls


def test_missing_env_skips_without_raising(db, monkeypatch, capsys):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    report = _report(db)
    assert telegram.send_report(report, db) is False
    row = db.execute("SELECT delivered_at FROM reports").fetchone()
    assert row["delivered_at"] is None
    assert "skipping delivery" in capsys.readouterr().out


def test_successful_send_stamps_delivered(db, tg_env, sent):
    report = _report(db)
    assert telegram.send_report(report, db) is True
    row = db.execute("SELECT delivered_at FROM reports").fetchone()
    assert row["delivered_at"] is not None


def test_send_failure_leaves_undelivered_and_no_token_in_output(db, tg_env, monkeypatch, capsys):
    async def _boom(*args, **kwargs):
        raise RuntimeError("secret-token leaked? no")

    monkeypatch.setattr(telegram, "_send", _boom)
    report = _report(db)
    assert telegram.send_report(report, db) is False
    assert db.execute("SELECT delivered_at FROM reports").fetchone()["delivered_at"] is None
    out = capsys.readouterr().out
    assert "secret-token" not in out


def test_retry_undelivered_delivers_backlog(db, tg_env, sent):
    _report(db, "2026-06-10")
    _report(db, "2026-06-11")
    db.execute(
        "INSERT INTO reports (report_date, digest_text, full_markdown, delivered_at)"
        " VALUES ('2026-06-09', 'd', 'f', datetime('now'))"
    )
    db.commit()
    assert telegram.retry_undelivered(db) == 2
    remaining = db.execute("SELECT COUNT(*) FROM reports WHERE delivered_at IS NULL").fetchone()[0]
    assert remaining == 0


def test_digest_truncated_at_paragraph(db, tg_env, sent):
    long_digest = "para one\n\n" + "x" * 4000
    report = _report(db, digest=long_digest)
    telegram.send_report(report, db)
    sent_digest = sent.call_args.args[2]
    assert len(sent_digest) <= telegram.DIGEST_CHAR_LIMIT
    assert sent_digest.startswith("para one")
