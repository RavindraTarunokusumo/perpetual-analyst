from __future__ import annotations

import sqlite3

from perpetual_analyst.store import db as db_module
from perpetual_analyst.store.models import Citation, Source, SourceCandidate

# ---------------------------------------------------------------------------
# Fresh-DB structure tests
# ---------------------------------------------------------------------------


def test_fresh_db_has_citations_table(db: sqlite3.Connection) -> None:
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='citations'"
    ).fetchone()
    assert row is not None


def test_fresh_db_has_source_candidates_table(db: sqlite3.Connection) -> None:
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='source_candidates'"
    ).fetchone()
    assert row is not None


def test_fresh_db_sources_has_status_column(db: sqlite3.Connection) -> None:
    cols = {row["name"] for row in db.execute("PRAGMA table_info(sources)")}
    assert "status" in cols


def test_fresh_db_sources_has_probation_until_column(db: sqlite3.Connection) -> None:
    cols = {row["name"] for row in db.execute("PRAGMA table_info(sources)")}
    assert "probation_until" in cols


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------


def test_ensure_columns_adds_missing_columns() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE sources (id INTEGER PRIMARY KEY, type TEXT, name TEXT)")
    db_module._ensure_columns(conn)
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(sources)")}
    assert "status" in cols
    assert "probation_until" in cols
    conn.close()


def test_ensure_columns_is_idempotent() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE sources (id INTEGER PRIMARY KEY, type TEXT, name TEXT)")
    db_module._ensure_columns(conn)
    db_module._ensure_columns(conn)  # second call must not raise
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(sources)")}
    assert "status" in cols
    assert "probation_until" in cols
    conn.close()


# ---------------------------------------------------------------------------
# Source.from_row round-trip
# ---------------------------------------------------------------------------


def test_source_from_row_new_fields(db: sqlite3.Connection) -> None:
    cur = db.execute("INSERT INTO sources (type, name) VALUES ('rss', 'Test Feed')")
    db.commit()
    row = db.execute("SELECT * FROM sources WHERE id = ?", (cur.lastrowid,)).fetchone()
    source = Source.from_row(row)
    assert source.status == "active"
    assert source.probation_until is None


# ---------------------------------------------------------------------------
# Citation.from_row round-trip
# ---------------------------------------------------------------------------


def test_citation_from_row(db: sqlite3.Connection) -> None:
    # Insert prerequisite report
    db.execute(
        "INSERT INTO reports (id, user_id, report_date, digest_text)"
        " VALUES (1, 1, '2026-06-11', 'x')"
    )
    # Insert prerequisite source + item
    src_cur = db.execute("INSERT INTO sources (type, name) VALUES ('rss', 'Feed')")
    item_cur = db.execute(
        "INSERT INTO items (source_id, content_hash, title) VALUES (?, 'hash_z', 'Z')",
        (src_cur.lastrowid,),
    )
    db.commit()

    cur = db.execute(
        "INSERT INTO citations (report_id, report_date, item_id, source_id)"
        " VALUES (1, '2026-06-11', ?, ?)",
        (item_cur.lastrowid, src_cur.lastrowid),
    )
    db.commit()
    row = db.execute("SELECT * FROM citations WHERE id = ?", (cur.lastrowid,)).fetchone()
    citation = Citation.from_row(row)
    assert citation.report_id == 1
    assert citation.report_date == "2026-06-11"
    assert citation.item_id == item_cur.lastrowid
    assert citation.source_id == src_cur.lastrowid
    assert citation.created_at is not None


# ---------------------------------------------------------------------------
# SourceCandidate.from_row round-trip
# ---------------------------------------------------------------------------


def test_source_candidate_from_row(db: sqlite3.Connection, sample_topic) -> None:
    cur = db.execute(
        "INSERT INTO source_candidates (topic_id, url, domain, rationale)"
        " VALUES (?, 'https://example.com', 'example.com', 'Good coverage')",
        (sample_topic.id,),
    )
    db.commit()
    row = db.execute("SELECT * FROM source_candidates WHERE id = ?", (cur.lastrowid,)).fetchone()
    candidate = SourceCandidate.from_row(row)
    assert candidate.topic_id == sample_topic.id
    assert candidate.url == "https://example.com"
    assert candidate.domain == "example.com"
    assert candidate.rationale == "Good coverage"
    assert candidate.status == "pending"
    assert candidate.created_at is not None
