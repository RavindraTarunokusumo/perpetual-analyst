"""Read-only view-model builders. All dashboard SELECTs live here."""

from __future__ import annotations

import sqlite3


def latest_report(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute("SELECT * FROM reports ORDER BY report_date DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def report_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, report_date, delivered_at, created_at " "FROM reports ORDER BY report_date DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def report_by_date(conn: sqlite3.Connection, report_date: str) -> dict | None:
    row = conn.execute("SELECT * FROM reports WHERE report_date = ?", (report_date,)).fetchone()
    return dict(row) if row else None


def topic_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT t.id, t.slug, t.name, t.brief,
                  (SELECT COUNT(*) FROM theses
                   WHERE topic_id = t.id AND status = 'active') AS active_theses
           FROM topics t WHERE t.active = 1 ORDER BY t.name"""
    ).fetchall()
    return [dict(r) for r in rows]


def topic_detail(conn: sqlite3.Connection, slug: str) -> dict | None:
    topic = conn.execute("SELECT * FROM topics WHERE slug = ?", (slug,)).fetchone()
    if topic is None:
        return None
    topic_id = topic["id"]
    dossier = conn.execute("SELECT * FROM dossiers WHERE topic_id = ?", (topic_id,)).fetchone()
    theses = conn.execute(
        "SELECT * FROM theses WHERE topic_id = ? AND status = 'active' " "ORDER BY confidence DESC",
        (topic_id,),
    ).fetchall()
    observations = conn.execute(
        "SELECT * FROM observations WHERE topic_id = ? AND status != 'expired' "
        "ORDER BY importance DESC, created_at DESC LIMIT 20",
        (topic_id,),
    ).fetchall()
    items = conn.execute(
        """SELECT i.* FROM items i
           WHERE i.source_id IN (
               SELECT source_id FROM topic_sources WHERE topic_id = ?)
           ORDER BY i.fetched_at DESC LIMIT 20""",
        (topic_id,),
    ).fetchall()
    return {
        "topic": dict(topic),
        "dossier": dict(dossier) if dossier else None,
        "theses": [dict(r) for r in theses],
        "observations": [dict(r) for r in observations],
        "items": [dict(r) for r in items],
    }


def thesis_detail(conn: sqlite3.Connection, thesis_id: int) -> dict | None:
    thesis = conn.execute("SELECT * FROM theses WHERE id = ?", (thesis_id,)).fetchone()
    if thesis is None:
        return None
    updates = conn.execute(
        "SELECT * FROM thesis_updates WHERE thesis_id = ? ORDER BY created_at",
        (thesis_id,),
    ).fetchall()
    return {"thesis": dict(thesis), "updates": [dict(r) for r in updates]}
