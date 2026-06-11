"""Tests for per-source quality scoring (quality.py). See SPEC §11."""

from __future__ import annotations

import sqlite3

import pytest

from perpetual_analyst.quality import bottom_decile, compute_source_quality, transition_probation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_source(db: sqlite3.Connection, name: str, status: str = "active") -> int:
    cur = db.execute(
        "INSERT INTO sources (type, name, status) VALUES ('rss', ?, ?)", (name, status)
    )
    db.commit()
    return cur.lastrowid


def _insert_item(
    db: sqlite3.Connection, source_id: int, content_hash: str, triage_score: float | None
) -> int:
    cur = db.execute(
        "INSERT INTO items (source_id, content_hash, triage_score) VALUES (?, ?, ?)",
        (source_id, content_hash, triage_score),
    )
    db.commit()
    return cur.lastrowid


def _insert_report(db: sqlite3.Connection, report_date: str) -> int:
    cur = db.execute("INSERT INTO reports (user_id, report_date) VALUES (1, ?)", (report_date,))
    db.commit()
    return cur.lastrowid


def _cite(
    db: sqlite3.Connection, report_id: int, report_date: str, item_id: int, source_id: int
) -> None:
    db.execute(
        "INSERT OR IGNORE INTO citations (report_id, report_date, item_id, source_id)"
        " VALUES (?, ?, ?, ?)",
        (report_id, report_date, item_id, source_id),
    )
    db.commit()


# ---------------------------------------------------------------------------
# hit_rate tests
# ---------------------------------------------------------------------------


def test_hit_rate_counts_only_above_threshold(db: sqlite3.Connection) -> None:
    """4 items: 2 with triage_score >= 0.4 → hit_rate 0.5."""
    sid = _insert_source(db, "src-a")
    _insert_item(db, sid, "h1", 0.8)  # hit
    _insert_item(db, sid, "h2", 0.4)  # hit (boundary)
    _insert_item(db, sid, "h3", 0.2)  # miss
    _insert_item(db, sid, "h4", 0.0)  # miss

    results = compute_source_quality(db)
    sq = next(r for r in results if r.source_id == sid)
    assert sq.total_items == 4
    assert sq.hit_rate == pytest.approx(0.5)


def test_null_triage_score_not_counted_as_hit(db: sqlite3.Connection) -> None:
    """NULL triage_score is treated as a miss, not a hit."""
    sid = _insert_source(db, "src-b")
    _insert_item(db, sid, "n1", None)  # NULL — must not count
    _insert_item(db, sid, "n2", 0.9)  # hit
    _insert_item(db, sid, "n3", 0.1)  # miss

    results = compute_source_quality(db)
    sq = next(r for r in results if r.source_id == sid)
    assert sq.total_items == 3
    assert sq.hit_rate == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# citation_rate tests
# ---------------------------------------------------------------------------


def test_citation_rate_counts_distinct_items(db: sqlite3.Connection) -> None:
    """2 of 4 items cited; same item cited in two reports counts once."""
    sid = _insert_source(db, "src-c")
    i1 = _insert_item(db, sid, "c1", 0.5)
    i2 = _insert_item(db, sid, "c2", 0.5)
    _insert_item(db, sid, "c3", 0.1)
    _insert_item(db, sid, "c4", 0.1)

    r1 = _insert_report(db, "2026-01-01")
    r2 = _insert_report(db, "2026-01-02")

    # i1 cited in both reports — should count once
    _cite(db, r1, "2026-01-01", i1, sid)
    _cite(db, r2, "2026-01-02", i1, sid)  # duplicate item_id
    _cite(db, r1, "2026-01-01", i2, sid)

    results = compute_source_quality(db)
    sq = next(r for r in results if r.source_id == sid)
    assert sq.citation_rate == pytest.approx(0.5)  # 2 distinct / 4 total


# ---------------------------------------------------------------------------
# score formula + persistence
# ---------------------------------------------------------------------------


def test_score_formula_and_persistence(db: sqlite3.Connection) -> None:
    """score = 0.5 * hit_rate + 0.5 * citation_rate; written to sources.quality_score."""
    sid = _insert_source(db, "src-d")
    i1 = _insert_item(db, sid, "d1", 0.8)  # hit
    i2 = _insert_item(db, sid, "d2", 0.8)  # hit
    _insert_item(db, sid, "d3", 0.1)  # miss
    _insert_item(db, sid, "d4", 0.1)  # miss

    r1 = _insert_report(db, "2026-02-01")
    _cite(db, r1, "2026-02-01", i1, sid)
    _cite(db, r1, "2026-02-01", i2, sid)

    results = compute_source_quality(db)
    sq = next(r for r in results if r.source_id == sid)

    # hit_rate = 2/4 = 0.5; citation_rate = 2/4 = 0.5; score = 0.5
    assert sq.hit_rate == pytest.approx(0.5)
    assert sq.citation_rate == pytest.approx(0.5)
    assert sq.score == pytest.approx(0.5)

    # Persisted to DB
    row = db.execute("SELECT quality_score FROM sources WHERE id = ?", (sid,)).fetchone()
    assert row["quality_score"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Zero-items source
# ---------------------------------------------------------------------------


def test_zero_item_source_excluded(db: sqlite3.Connection) -> None:
    """A source with no items must be absent from results and quality_score stays NULL."""
    sid = _insert_source(db, "src-empty")
    # no items inserted

    results = compute_source_quality(db)
    ids = [r.source_id for r in results]
    assert sid not in ids

    row = db.execute("SELECT quality_score FROM sources WHERE id = ?", (sid,)).fetchone()
    assert row["quality_score"] is None


# ---------------------------------------------------------------------------
# bottom_decile tests
# ---------------------------------------------------------------------------


def test_bottom_decile_worst_source_appears(db: sqlite3.Connection) -> None:
    """A clearly worst source (0 hits, 0 citations, many items) appears in bottom_decile."""
    good = _insert_source(db, "good-src")
    bad = _insert_source(db, "bad-src")

    # good source: 10 high-scoring, all cited
    r1 = _insert_report(db, "2026-03-01")
    for i in range(10):
        item_id = _insert_item(db, good, f"g{i}", 0.9)
        _cite(db, r1, "2026-03-01", item_id, good)

    # bad source: 10 low-scoring, none cited
    for i in range(10):
        _insert_item(db, bad, f"b{i}", 0.0)

    decile = bottom_decile(db)
    ids = [r.source_id for r in decile]
    assert bad in ids
    assert good not in ids


def test_bottom_decile_excludes_probation(db: sqlite3.Connection) -> None:
    """Sources with status='probation' are excluded even if their metrics are terrible."""
    prob = _insert_source(db, "prob-src", status="probation")
    for i in range(10):
        _insert_item(db, prob, f"p{i}", 0.0)

    decile = bottom_decile(db)
    ids = [r.source_id for r in decile]
    assert prob not in ids


def test_bottom_decile_min_items_threshold(db: sqlite3.Connection) -> None:
    """Sources with fewer than min_items are excluded from bottom_decile."""
    small = _insert_source(db, "small-src")
    _insert_item(db, small, "s1", 0.0)
    _insert_item(db, small, "s2", 0.0)
    # only 2 items — below default min_items=5

    decile = bottom_decile(db)
    ids = [r.source_id for r in decile]
    assert small not in ids


# ---------------------------------------------------------------------------
# transition_probation tests
# ---------------------------------------------------------------------------


def _insert_source_with_probation(
    db: sqlite3.Connection,
    name: str,
    probation_until: str | None,
) -> int:
    cur = db.execute(
        "INSERT INTO sources (type, name, status, probation_until)"
        " VALUES ('rss', ?, 'probation', ?)",
        (name, probation_until),
    )
    db.commit()
    return cur.lastrowid


def test_transition_probation_past_date_becomes_active(db: sqlite3.Connection) -> None:
    """A probation source whose probation_until is in the past is promoted to active."""
    sid = _insert_source_with_probation(db, "past-prob", "2020-01-01 00:00:00")

    count = transition_probation(db)

    assert count == 1
    row = db.execute("SELECT status FROM sources WHERE id = ?", (sid,)).fetchone()
    assert row["status"] == "active"


def test_transition_probation_future_date_stays_probation(db: sqlite3.Connection) -> None:
    """A probation source with a future probation_until is not promoted."""
    sid = _insert_source_with_probation(db, "future-prob", "2099-01-01 00:00:00")

    count = transition_probation(db)

    assert count == 0
    row = db.execute("SELECT status FROM sources WHERE id = ?", (sid,)).fetchone()
    assert row["status"] == "probation"


def test_transition_probation_null_probation_until_stays(db: sqlite3.Connection) -> None:
    """A probation source with NULL probation_until is left as-is."""
    sid = _insert_source_with_probation(db, "null-prob", None)

    count = transition_probation(db)

    assert count == 0
    row = db.execute("SELECT status FROM sources WHERE id = ?", (sid,)).fetchone()
    assert row["status"] == "probation"


def test_transition_probation_returns_correct_count(db: sqlite3.Connection) -> None:
    """Returns the exact number of sources transitioned."""
    _insert_source_with_probation(db, "old1", "2020-01-01 00:00:00")
    _insert_source_with_probation(db, "old2", "2021-06-15 12:00:00")
    _insert_source_with_probation(db, "future", "2099-01-01 00:00:00")
    _insert_source_with_probation(db, "no-date", None)

    count = transition_probation(db)

    assert count == 2
