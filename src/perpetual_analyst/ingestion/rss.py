"""RSS/Atom feed fetcher: httpx + feedparser + trafilatura. See SPEC §12 Phase 2."""

from __future__ import annotations

import hashlib
import sqlite3
import time

import feedparser
import httpx
import trafilatura

from perpetual_analyst.store.db import insert_item
from perpetual_analyst.store.models import Source

MAX_FETCH_ERRORS = 5
_TIMEOUT_SECONDS = 30.0


def _entry_timestamp(entry: feedparser.FeedParserDict) -> str | None:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            return time.strftime("%Y-%m-%d %H:%M:%S", parsed)
    return None


def _extract_full_text(url: str | None) -> str | None:
    if not url:
        return None
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            return trafilatura.extract(downloaded)
    except Exception:
        pass
    return None


def _record_fetch_error(source_id: int, conn: sqlite3.Connection) -> None:
    conn.execute(
        "UPDATE sources SET fetch_error_count = fetch_error_count + 1 WHERE id = ?",
        (source_id,),
    )
    conn.execute(
        "UPDATE sources SET active = 0 WHERE id = ? AND fetch_error_count >= ?",
        (source_id, MAX_FETCH_ERRORS),
    )


def fetch_rss(source: Source, conn: sqlite3.Connection) -> int:
    """Fetch new entries for one RSS source. Returns the count of newly inserted items.

    Feed-level failures increment fetch_error_count (source deactivated at
    MAX_FETCH_ERRORS); item-level extraction failures fall back to the feed summary.
    """
    try:
        response = httpx.get(source.url, timeout=_TIMEOUT_SECONDS, follow_redirects=True)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        if feed.bozo and not feed.entries:
            raise ValueError(f"unparseable feed: {source.url}")
    except Exception:
        _record_fetch_error(source.id, conn)
        conn.commit()
        return 0

    inserted = 0
    for entry in feed.entries:
        published = _entry_timestamp(entry)
        if source.last_fetched_at and published and published <= source.last_fetched_at:
            continue
        link = getattr(entry, "link", None)
        text = _extract_full_text(link) or getattr(entry, "summary", None)
        if not text or not text.strip():
            continue
        is_new = insert_item(
            conn,
            source_id=source.id,
            content_hash=hashlib.sha256(text.strip().encode()).hexdigest(),
            title=getattr(entry, "title", None),
            url=link,
            author=getattr(entry, "author", None),
            published_at=published,
            raw_text=text,
        )
        if is_new:
            inserted += 1

    conn.execute(
        "UPDATE sources SET last_fetched_at = datetime('now'), fetch_error_count = 0"
        " WHERE id = ?",
        (source.id,),
    )
    conn.commit()
    return inserted
