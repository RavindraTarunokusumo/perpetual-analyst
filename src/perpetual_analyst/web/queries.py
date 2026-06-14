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


def items_feed(
    conn: sqlite3.Connection,
    status: str | None = None,
    source_id: int | None = None,
    limit: int = 100,
) -> list[dict]:
    clauses, params = [], []
    if status:
        clauses.append("i.status = ?")
        params.append(status)
    if source_id:
        clauses.append("i.source_id = ?")
        params.append(source_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    rows = conn.execute(
        f"""SELECT i.id, i.title, i.url, i.triage_summary, i.triage_score,
                   i.status, i.fetched_at, s.name AS source_name
            FROM items i LEFT JOIN sources s ON s.id = i.source_id
            {where} ORDER BY i.fetched_at DESC LIMIT ?""",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def ops_overview(conn: sqlite3.Connection) -> dict:
    sources = conn.execute(
        "SELECT id, type, name, active, last_fetched_at, fetch_error_count "
        "FROM sources ORDER BY type, name"
    ).fetchall()
    counts = conn.execute("SELECT status, COUNT(*) AS n FROM items GROUP BY status").fetchall()
    undelivered = conn.execute(
        "SELECT COUNT(*) AS n FROM reports WHERE delivered_at IS NULL"
    ).fetchone()["n"]
    return {
        "sources": [dict(r) for r in sources],
        "inbox_sources": [dict(r) for r in sources if r["type"] == "inbox" and r["active"]],
        "status_counts": {r["status"]: r["n"] for r in counts},
        "undelivered": undelivered,
    }


def all_dossiers(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT t.slug, t.name, d.content, d.updated_at
           FROM topics t JOIN dossiers d ON d.topic_id = t.id
           WHERE t.active = 1 ORDER BY t.name"""
    ).fetchall()
    return [dict(r) for r in rows]
