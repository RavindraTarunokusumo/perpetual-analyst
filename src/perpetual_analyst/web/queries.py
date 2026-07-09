"""Read-only view-model builders. All dashboard SELECTs live here."""

from __future__ import annotations

import sqlite3


def confidence_points(
    updates: list[dict],
    width: int = 560,
    height: int = 96,
    pad: int = 6,
) -> str:
    """Return an SVG polyline points string for a step chart of confidence history."""
    values: list[float] = []
    if updates:
        before = updates[0].get("confidence_before")
        if before is not None:
            values.append(float(before))
        for row in updates:
            after = row.get("confidence_after")
            if after is not None:
                values.append(float(after))
    if len(values) < 2:
        return ""

    n = len(values)
    span_x = width - 2 * pad
    span_y = height - 2 * pad

    def x_at(i: int) -> float:
        return pad + i * span_x / n

    def y_at(conf: float) -> float:
        return pad + (1.0 - conf) * span_y

    xs = [x_at(i) for i in range(n + 1)]
    ys = [round(y_at(v), 1) for v in values]

    coords: list[tuple[float, float]] = [(round(xs[0], 1), ys[0])]
    for i in range(1, n):
        coords.append((round(xs[i], 1), ys[i - 1]))
        coords.append((round(xs[i], 1), ys[i]))
    coords.append((round(xs[n], 1), ys[n - 1]))

    return " ".join(f"{x},{y}" for x, y in coords)


def latest_report(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute("SELECT * FROM reports ORDER BY report_date DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def today_changes(conn: sqlite3.Connection, report_date: str) -> list[dict]:
    topics = conn.execute(
        "SELECT id, slug, name FROM topics WHERE active = 1 ORDER BY name"
    ).fetchall()
    delta_rows = conn.execute(
        """SELECT th.topic_id, tu.thesis_id, th.statement,
                  tu.confidence_before AS before, tu.confidence_after AS after,
                  tu.change
           FROM thesis_updates tu
           JOIN theses th ON th.id = tu.thesis_id
           JOIN topics t ON t.id = th.topic_id
           WHERE t.active = 1 AND th.status = 'active'
             AND date(tu.created_at) = ?
           ORDER BY th.topic_id, tu.created_at""",
        (report_date,),
    ).fetchall()
    obs_rows = conn.execute(
        """SELECT topic_id, COUNT(*) AS n FROM observations
           WHERE date(created_at) = ? GROUP BY topic_id""",
        (report_date,),
    ).fetchall()
    deltas_by_topic: dict[int, list[dict]] = {}
    for row in delta_rows:
        deltas_by_topic.setdefault(row["topic_id"], []).append(
            {
                "thesis_id": row["thesis_id"],
                "statement": row["statement"],
                "before": row["before"],
                "after": row["after"],
                "change": row["change"],
            }
        )
    obs_by_topic = {row["topic_id"]: row["n"] for row in obs_rows}
    result = []
    for topic in topics:
        tid = topic["id"]
        deltas = deltas_by_topic.get(tid, [])
        new_obs = obs_by_topic.get(tid, 0)
        result.append(
            {
                "slug": topic["slug"],
                "name": topic["name"],
                "deltas": deltas,
                "new_observations": new_obs,
                "quiet": not deltas and new_obs == 0,
            }
        )
    result.sort(key=lambda row: (row["quiet"], -len(row["deltas"])))
    return result


def report_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, report_date, delivered_at, created_at FROM reports ORDER BY report_date DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def report_by_date(conn: sqlite3.Connection, report_date: str) -> dict | None:
    row = conn.execute("SELECT * FROM reports WHERE report_date = ?", (report_date,)).fetchone()
    return dict(row) if row else None


def topic_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT t.id, t.slug, t.name, t.brief,
                  (SELECT COUNT(*) FROM theses
                   WHERE topic_id = t.id AND status = 'active') AS active_theses,
                  (SELECT updated_at FROM dossiers WHERE topic_id = t.id) AS dossier_updated_at,
                  (SELECT statement FROM theses
                   WHERE topic_id = t.id AND status = 'active'
                   ORDER BY confidence DESC LIMIT 1) AS top_thesis,
                  (SELECT confidence FROM theses
                   WHERE topic_id = t.id AND status = 'active'
                   ORDER BY confidence DESC LIMIT 1) AS top_confidence,
                  (SELECT COUNT(*) FROM thesis_updates tu
                   JOIN theses th ON th.id = tu.thesis_id
                   WHERE th.topic_id = t.id
                     AND date(tu.created_at) = date('now')) AS updates_today
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
        "SELECT * FROM theses WHERE topic_id = ? AND status = 'active' ORDER BY confidence DESC",
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


def topic_id_for_slug(conn: sqlite3.Connection, slug: str) -> int | None:
    row = conn.execute("SELECT id FROM topics WHERE slug = ?", (slug,)).fetchone()
    return row["id"] if row else None


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
    if source_id is not None:
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


def inbox_sources(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, name FROM sources WHERE type = 'inbox' AND active = 1 ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


def all_dossiers(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT t.slug, t.name, d.content, d.updated_at
           FROM topics t JOIN dossiers d ON d.topic_id = t.id
           WHERE t.active = 1 ORDER BY t.name"""
    ).fetchall()
    return [dict(r) for r in rows]
