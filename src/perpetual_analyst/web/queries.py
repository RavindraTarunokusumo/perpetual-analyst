"""Read-only view-model builders. All dashboard SELECTs live here."""

from __future__ import annotations

import sqlite3


def latest_report(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute("SELECT * FROM reports ORDER BY report_date DESC LIMIT 1").fetchone()
    return dict(row) if row else None
