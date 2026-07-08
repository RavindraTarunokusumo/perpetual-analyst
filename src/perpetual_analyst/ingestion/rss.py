"""RSS/Atom feed fetcher: httpx + feedparser + trafilatura. See SPEC §12 Phase 2."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import feedparser
import trafilatura

from perpetual_analyst.store.db import insert_item
from perpetual_analyst.store.models import Item, Source

logger = logging.getLogger(__name__)


def _parse_as_utc_naive(s: str) -> datetime | None:
    """Parse ISO 8601 or SQLite datetime string to a UTC-naive datetime for comparison."""
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            return dt.astimezone(UTC).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def _entry_published_iso(entry: feedparser.FeedParserDict) -> str | None:
    """Return ISO 8601 string from a feedparser entry, or None."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", entry.published_parsed)
    if hasattr(entry, "published") and entry.published:
        try:
            return parsedate_to_datetime(entry.published).isoformat()
        except Exception:
            return entry.published
    return None


def _extract_text(url: str | None, summary: str | None) -> str | None:
    """Try trafilatura for full text; fall back to feed summary."""
    if url:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                extracted = trafilatura.extract(downloaded)
                if extracted:
                    return extracted
        except Exception:
            pass
    return summary or None


def fetch_rss(source: Source, conn: sqlite3.Connection) -> list[Item]:
    """Fetch and ingest items from an RSS/Atom source.

    Returns the list[Item] of newly inserted items only.
    On exception: increments fetch_error_count; deactivates source if count >= 5.
    """
    try:
        feed = feedparser.parse(source.url)
        new_items: list[Item] = []

        for entry in feed.entries:
            published_iso = _entry_published_iso(entry)

            # Filter entries older than last_fetched_at when set (compare as datetimes)
            if source.last_fetched_at and published_iso:
                pub_dt = _parse_as_utc_naive(published_iso)
                last_dt = _parse_as_utc_naive(source.last_fetched_at)
                if pub_dt is not None and last_dt is not None and pub_dt <= last_dt:
                    continue

            url = entry.get("link") or None
            title = entry.get("title") or None
            summary = entry.get("summary") or entry.get("description") or None
            author = entry.get("author") or None

            raw_text = _extract_text(url, summary)

            # Hash on url+title+summary to deduplicate reliably
            hash_input = (url or "") + (title or "") + (summary or "")
            content_hash = hashlib.sha256(hash_input.encode()).hexdigest()

            inserted = insert_item(
                conn,
                source.id,
                content_hash,
                title=title,
                url=url,
                author=author,
                published_at=published_iso,
                raw_text=raw_text,
            )
            if inserted:
                row = conn.execute(
                    "SELECT * FROM items WHERE content_hash = ?", (content_hash,)
                ).fetchone()
                new_items.append(Item.from_row(row))

        conn.execute(
            "UPDATE sources SET last_fetched_at = datetime('now') WHERE id = ?",
            (source.id,),
        )
        conn.commit()
        return new_items

    except Exception:
        logger.warning("fetch_rss failed for source %d", source.id, exc_info=True)
        new_count = source.fetch_error_count + 1
        if new_count >= 5:
            conn.execute(
                "UPDATE sources SET fetch_error_count = ?, active = 0 WHERE id = ?",
                (new_count, source.id),
            )
        else:
            conn.execute(
                "UPDATE sources SET fetch_error_count = ? WHERE id = ?",
                (new_count, source.id),
            )
        conn.commit()
        return []
