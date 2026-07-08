"""Daily pipeline orchestrator. Entry point: python -m perpetual_analyst.daily_run"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from perpetual_analyst.analyst.agent import make_client
from perpetual_analyst.analyst.triage import triage_items
from perpetual_analyst.config import load_settings
from perpetual_analyst.delivery.telegram import retry_undelivered, send_report
from perpetual_analyst.ingestion.inbox import get_or_create_inbox_source, scan_inbox
from perpetual_analyst.ingestion.rss import fetch_rss
from perpetual_analyst.report.assemble import assemble_report
from perpetual_analyst.store.db import init_db
from perpetual_analyst.store.models import Source, Topic

load_dotenv()
# The substrate + Qwen client read secrets (QWEN_CLOUD_API_KEY, DATABASE_URL) from
# Nexus/.env; load it here so make_client("qwen") works before substrate imports.
load_dotenv(Path(__file__).resolve().parents[2] / "Nexus" / ".env")

logger = logging.getLogger(__name__)


def main(dry_run: bool = False, topic_slug: str | None = None) -> None:
    """Run the full daily pipeline."""
    db_path = os.environ.get("ANALYST_DB_PATH", "data/analyst.db")
    conn = init_db(db_path)
    settings = load_settings()

    # Catch up any stale deliveries
    try:
        retry_undelivered(conn)
    except Exception:
        logger.exception("retry_undelivered failed; continuing")

    # Build client (skip for dry_run)
    client = None if dry_run else make_client("qwen")

    # Resolve topics
    if topic_slug:
        row = conn.execute("SELECT * FROM topics WHERE slug = ?", (topic_slug,)).fetchone()
        topics: list[Topic] = [Topic.from_row(row)] if row else []
    else:
        rows = conn.execute("SELECT * FROM topics WHERE active = 1").fetchall()
        topics = [Topic.from_row(r) for r in rows]

    if not topics:
        print("[daily_run] No active topics — nothing to do.")
        return

    topic_analyses: dict = {}
    successes = 0
    failures = 0

    for topic in topics:
        try:
            source_id = get_or_create_inbox_source(conn, topic.id, topic.slug)
            items = scan_inbox(topic.slug, topic.id, source_id, conn)

            rss_rows = conn.execute(
                """SELECT s.* FROM sources s
                   JOIN topic_sources ts ON ts.source_id = s.id
                   WHERE ts.topic_id = ? AND s.type = 'rss' AND s.active = 1""",
                (topic.id,),
            ).fetchall()
            for rss_row in rss_rows:
                items += fetch_rss(Source.from_row(rss_row), conn)

            if client is not None and items:
                items = triage_items(items, topic.brief or "", client, settings, conn)

            print(f"[daily_run] topic={topic.slug} items={len(items)}")

            if dry_run:
                bundle = None
            else:
                from perpetual_analyst.analyst import synthesis

                bundle, write_result, _tokens = synthesis.run_daily_for_topic(
                    topic.slug,
                    topic.name,
                    topic.brief,
                    items,
                )
                print(
                    f"[daily_run] topic={topic.slug} "
                    f"corpus_ingested={write_result.get('corpus_ingested', 0)}"
                )
                print(f"[daily_run] topic={topic.slug} narrative={write_result}")

            if bundle is not None:
                topic_analyses[topic.slug] = bundle
            successes += 1
        except Exception:
            logger.exception("[daily_run] topic=%s failed", topic.slug)
            failures += 1

    # Assemble and deliver (isolated so a Telegram failure leaves the report for retry)
    if not dry_run and topic_analyses:
        try:
            report_id = assemble_report(topic_analyses, str(date.today()), conn, client, settings)
            send_report(report_id, conn)
        except Exception:
            logger.exception("[daily_run] assemble/deliver failed — report persisted for retry")

    print(f"[daily_run] done — topics={len(topics)} successes={successes} failures={failures}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the daily analyst pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts, skip API/Telegram")
    parser.add_argument("--topic", default=None, help="Run for a single topic slug")
    args = parser.parse_args()
    main(dry_run=args.dry_run, topic_slug=args.topic)
