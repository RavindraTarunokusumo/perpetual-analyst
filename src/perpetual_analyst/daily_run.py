"""Daily pipeline orchestrator: sync -> ingest -> triage -> analyze -> assemble -> deliver.

Entry point: python -m perpetual_analyst.daily_run
Per-stage and per-topic failures are isolated: one broken topic or stage never
kills the rest of the run. Exit 0 even on partial success (SPEC §12 Phase 3).
"""

from __future__ import annotations

import sqlite3
import sys

import openai
from dotenv import load_dotenv

from perpetual_analyst.analyst.agent import make_client, run_topic
from perpetual_analyst.analyst.triage import select_analyst_items, triage_items
from perpetual_analyst.config import (
    Settings,
    load_settings,
    load_sources,
    load_topics,
    sync_config,
)
from perpetual_analyst.delivery.telegram import retry_undelivered
from perpetual_analyst.ingestion.inbox import scan_inbox
from perpetual_analyst.ingestion.rss import fetch_rss
from perpetual_analyst.report.assemble import assemble_report, persist_report
from perpetual_analyst.store.db import init_db
from perpetual_analyst.store.models import Item, Source, Topic


def _active_topics(conn: sqlite3.Connection) -> list[Topic]:
    rows = conn.execute("SELECT * FROM topics WHERE active = 1").fetchall()
    return [Topic.from_row(row) for row in rows]


def _topic_sources(topic_id: int, source_type: str, conn: sqlite3.Connection) -> list[Source]:
    rows = conn.execute(
        """SELECT s.* FROM sources s
           JOIN topic_sources ts ON ts.source_id = s.id
           WHERE ts.topic_id = ? AND s.type = ? AND s.active = 1""",
        (topic_id, source_type),
    ).fetchall()
    return [Source.from_row(row) for row in rows]


def _untriaged_items(topic_id: int, conn: sqlite3.Connection) -> list[Item]:
    rows = conn.execute(
        """SELECT i.* FROM items i
           JOIN topic_sources ts ON ts.source_id = i.source_id AND ts.topic_id = ?
           WHERE i.status = 'new' AND i.triage_score IS NULL""",
        (topic_id,),
    ).fetchall()
    return [Item.from_row(row) for row in rows]


def run_daily(
    conn: sqlite3.Connection,
    client: openai.OpenAI | None,
    settings: Settings,
    topic_slug: str | None = None,
    dry_run: bool = False,
) -> None:
    try:
        sync_config(conn, load_topics(), load_sources())
    except Exception as exc:
        print(f"[daily] config sync failed: {exc}")

    topics = _active_topics(conn)
    if topic_slug:
        topics = [t for t in topics if t.slug == topic_slug]

    for topic in topics:
        for source in _topic_sources(topic.id, "inbox", conn):
            try:
                scan_inbox(topic.slug, topic.id, source.id, conn)
            except Exception as exc:
                print(f"[daily] inbox scan failed for {topic.slug}: {exc}")
        for source in _topic_sources(topic.id, "rss", conn):
            try:
                fetch_rss(source, conn)
            except Exception as exc:
                print(f"[daily] rss fetch failed for {source.name}: {exc}")

    already = conn.execute("SELECT 1 FROM reports WHERE report_date = date('now')").fetchone()
    if already:
        print("[daily] report for today already exists - skipping analysis")
    else:
        results = []
        for topic in topics:
            try:
                pending = _untriaged_items(topic.id, conn)
                if pending and not dry_run:
                    triage_items(pending, topic.brief or "", client, settings, conn)
                keep = select_analyst_items(topic.id, conn)
                analysis = run_topic(topic, keep, conn, client, settings, dry_run=dry_run)
                if analysis is not None:
                    results.append((topic, analysis))
            except Exception as exc:
                print(f"[daily] topic {topic.slug} failed: {exc}")

        if not dry_run and results:
            try:
                report_date = conn.execute("SELECT date('now')").fetchone()[0]
                digest_text, full_markdown = assemble_report(
                    results, conn, client, settings, report_date
                )
                persist_report(report_date, digest_text, full_markdown, conn)
            except Exception as exc:
                print(f"[daily] assemble/persist failed: {exc}")

    if not dry_run:
        try:
            delivered = retry_undelivered(conn)
            print(f"[daily] delivered {delivered} report(s)")
        except Exception as exc:
            print(f"[daily] delivery stage failed: {exc}")


def force_utf8_stdout() -> None:
    """Piped/scheduled output on Windows defaults to cp1252; prompts contain unicode."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    force_utf8_stdout()
    load_dotenv()
    conn = init_db()
    try:
        run_daily(conn, make_client(), load_settings())
    finally:
        conn.close()


if __name__ == "__main__":
    main()
