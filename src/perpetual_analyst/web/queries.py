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
