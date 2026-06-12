from __future__ import annotations

import httpx
import pytest

from perpetual_analyst.ingestion import rss
from perpetual_analyst.store.models import Source

RSS_XML = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test Feed</title>
<item><title>First Post</title><link>https://example.com/1</link>
<pubDate>Mon, 08 Jun 2026 12:00:00 GMT</pubDate>
<description>Summary one</description></item>
<item><title>Second Post</title><link>https://example.com/2</link>
<pubDate>Wed, 10 Jun 2026 12:00:00 GMT</pubDate>
<description>Summary two</description></item>
</channel></rss>"""


@pytest.fixture
def rss_source(db):
    cur = db.execute(
        "INSERT INTO sources (type, url, name) VALUES"
        " ('rss', 'https://example.com/feed', 'Test Feed')"
    )
    db.commit()
    row = db.execute("SELECT * FROM sources WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Source.from_row(row)


class _FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        pass


@pytest.fixture
def feed_ok(monkeypatch):
    monkeypatch.setattr(rss.httpx, "get", lambda *a, **kw: _FakeResponse(RSS_XML))
    monkeypatch.setattr(rss.trafilatura, "fetch_url", lambda url: f"<html>{url}</html>")
    monkeypatch.setattr(rss.trafilatura, "extract", lambda html: f"Full text from {html}")


def test_fetch_inserts_new_items(db, rss_source, feed_ok):
    count = rss.fetch_rss(rss_source, db)
    assert count == 2
    rows = db.execute("SELECT title, raw_text, status FROM items ORDER BY id").fetchall()
    assert [r["title"] for r in rows] == ["First Post", "Second Post"]
    assert all("Full text" in r["raw_text"] for r in rows)
    src = db.execute("SELECT * FROM sources WHERE id = ?", (rss_source.id,)).fetchone()
    assert src["last_fetched_at"] is not None
    assert src["fetch_error_count"] == 0


def test_since_last_fetch_skips_old_entries(db, rss_source, feed_ok):
    db.execute(
        "UPDATE sources SET last_fetched_at = '2026-06-09 00:00:00' WHERE id = ?",
        (rss_source.id,),
    )
    db.commit()
    src = Source.from_row(
        db.execute("SELECT * FROM sources WHERE id = ?", (rss_source.id,)).fetchone()
    )
    count = rss.fetch_rss(src, db)
    assert count == 1
    titles = [r["title"] for r in db.execute("SELECT title FROM items").fetchall()]
    assert titles == ["Second Post"]


def test_refetch_dedupes_silently(db, rss_source, feed_ok):
    assert rss.fetch_rss(rss_source, db) == 2
    assert rss.fetch_rss(rss_source, db) == 0
    assert db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2


def test_extraction_failure_falls_back_to_summary(db, rss_source, monkeypatch):
    monkeypatch.setattr(rss.httpx, "get", lambda *a, **kw: _FakeResponse(RSS_XML))
    monkeypatch.setattr(rss.trafilatura, "fetch_url", lambda url: None)
    count = rss.fetch_rss(rss_source, db)
    assert count == 2
    texts = [r["raw_text"] for r in db.execute("SELECT raw_text FROM items").fetchall()]
    assert texts == ["Summary one", "Summary two"]


def test_feed_error_increments_count(db, rss_source, monkeypatch):
    def _boom(*a, **kw):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(rss.httpx, "get", _boom)
    assert rss.fetch_rss(rss_source, db) == 0
    src = db.execute("SELECT * FROM sources WHERE id = ?", (rss_source.id,)).fetchone()
    assert src["fetch_error_count"] == 1
    assert src["active"] == 1


def test_source_deactivated_after_five_errors(db, rss_source, monkeypatch):
    db.execute("UPDATE sources SET fetch_error_count = 4 WHERE id = ?", (rss_source.id,))
    db.commit()

    def _boom(*a, **kw):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(rss.httpx, "get", _boom)
    rss.fetch_rss(rss_source, db)
    src = db.execute("SELECT * FROM sources WHERE id = ?", (rss_source.id,)).fetchone()
    assert src["fetch_error_count"] == 5
    assert src["active"] == 0


def test_success_resets_error_count(db, rss_source, feed_ok):
    db.execute("UPDATE sources SET fetch_error_count = 3 WHERE id = ?", (rss_source.id,))
    db.commit()
    rss.fetch_rss(rss_source, db)
    src = db.execute("SELECT * FROM sources WHERE id = ?", (rss_source.id,)).fetchone()
    assert src["fetch_error_count"] == 0


UNDATED_XML = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test Feed</title>
<item><title>No Date Post</title><link>https://example.com/nodate</link>
<description>Summary undated</description></item>
</channel></rss>"""


def test_undated_entry_always_taken_and_deduped(db, rss_source, monkeypatch):
    monkeypatch.setattr(rss.httpx, "get", lambda *a, **kw: _FakeResponse(UNDATED_XML))
    monkeypatch.setattr(rss.trafilatura, "fetch_url", lambda url: None)
    assert rss.fetch_rss(rss_source, db) == 1
    # undated entries pass the since-last-fetch filter on refetch; dedupe catches them
    src = Source.from_row(
        db.execute("SELECT * FROM sources WHERE id = ?", (rss_source.id,)).fetchone()
    )
    assert rss.fetch_rss(src, db) == 0
    row = db.execute("SELECT published_at FROM items").fetchone()
    assert row["published_at"] is None
