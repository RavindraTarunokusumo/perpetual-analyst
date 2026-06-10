"""Daily pipeline orchestrator. Entry point: python -m perpetual_analyst.daily_run"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import date

from dotenv import load_dotenv

from perpetual_analyst.analyst.agent import make_client, run_topic
from perpetual_analyst.config import load_settings
from perpetual_analyst.delivery.telegram import retry_undelivered, send_report
from perpetual_analyst.ingestion.inbox import get_or_create_inbox_source, scan_inbox
from perpetual_analyst.report.assemble import assemble_report
from perpetual_analyst.store.db import init_db
from perpetual_analyst.store.models import Topic

load_dotenv()

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
    client = None if dry_run else make_client()

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
            print(f"[daily_run] topic={topic.slug} items={len(items)}")

            result = run_topic(topic, items, conn, client, settings, dry_run=dry_run)

            if result is not None:
                topic_analyses[topic.slug] = result
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
