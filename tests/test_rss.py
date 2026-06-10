"""Tests for ingestion/rss.py — RSS/Atom feed fetching."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

from perpetual_analyst.ingestion.rss import fetch_rss
from perpetual_analyst.store.models import Source

_FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <item>
      <title>Article One</title>
      <link>https://example.com/article-1</link>
      <description>Summary of article one about AI.</description>
      <pubDate>Mon, 01 Jan 2024 00:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Article Two</title>
      <link>https://example.com/article-2</link>
      <description>Summary of article two about ML.</description>
      <pubDate>Tue, 02 Jan 2024 00:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""


def _make_source(
    db: sqlite3.Connection,
    url: str = "https://example.com/feed.xml",
    last_fetched_at: str | None = None,
    fetch_error_count: int = 0,
    active: int = 1,
) -> Source:
    cur = db.execute(
        "INSERT INTO sources (type, url, name, last_fetched_at, fetch_error_count, active)"
        " VALUES ('rss', ?, 'Test RSS', ?, ?, ?)",
        (url, last_fetched_at, fetch_error_count, active),
    )
    db.commit()
    row = db.execute("SELECT * FROM sources WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Source.from_row(row)


def test_fetch_rss_returns_new_items(db: sqlite3.Connection) -> None:
    """Feed with 2 entries should insert and return 2 new items."""
    import feedparser as _fp

    parsed = _fp.parse(_FEED_XML)
    source = _make_source(db)
    with (
        patch("perpetual_analyst.ingestion.rss.feedparser.parse", return_value=parsed),
        patch("perpetual_analyst.ingestion.rss.trafilatura.fetch_url", return_value=None),
    ):
        items = fetch_rss(source, db)
    assert len(items) == 2
    titles = {i.title for i in items}
    assert "Article One" in titles
    assert "Article Two" in titles


def test_fetch_rss_deduplicates(db: sqlite3.Connection) -> None:
    """Calling fetch_rss twice with the same feed returns 0 new items on second call."""
    import feedparser as _fp

    parsed = _fp.parse(_FEED_XML)
    source = _make_source(db)
    with (
        patch("perpetual_analyst.ingestion.rss.feedparser.parse", return_value=parsed),
        patch("perpetual_analyst.ingestion.rss.trafilatura.fetch_url", return_value=None),
    ):
        fetch_rss(source, db)
        # Re-fetch the source with updated last_fetched_at
        row = db.execute("SELECT * FROM sources WHERE id = ?", (source.id,)).fetchone()
        updated_source = Source.from_row(row)
        second = fetch_rss(updated_source, db)
    assert len(second) == 0


def test_fetch_rss_updates_last_fetched_at(db: sqlite3.Connection) -> None:
    """source.last_fetched_at should be set after a successful fetch."""
    import feedparser as _fp

    parsed = _fp.parse(_FEED_XML)
    source = _make_source(db)
    assert source.last_fetched_at is None
    with (
        patch("perpetual_analyst.ingestion.rss.feedparser.parse", return_value=parsed),
        patch("perpetual_analyst.ingestion.rss.trafilatura.fetch_url", return_value=None),
    ):
        fetch_rss(source, db)
    row = db.execute("SELECT last_fetched_at FROM sources WHERE id = ?", (source.id,)).fetchone()
    assert row["last_fetched_at"] is not None


def test_fetch_rss_increments_error_count_on_failure(db: sqlite3.Connection) -> None:
    """A fetch exception should increment fetch_error_count by 1."""
    source = _make_source(db)
    with patch("feedparser.parse", side_effect=Exception("network error")):
        fetch_rss(source, db)
    row = db.execute("SELECT fetch_error_count FROM sources WHERE id = ?", (source.id,)).fetchone()
    assert row["fetch_error_count"] == 1


def test_fetch_rss_deactivates_source_after_5_errors(db: sqlite3.Connection) -> None:
    """When fetch_error_count reaches 5, source should be set to active=0."""
    source = _make_source(db, fetch_error_count=4)
    with patch("feedparser.parse", side_effect=Exception("network error")):
        fetch_rss(source, db)
    row = db.execute(
        "SELECT active, fetch_error_count FROM sources WHERE id = ?", (source.id,)
    ).fetchone()
    assert row["fetch_error_count"] == 5
    assert row["active"] == 0
