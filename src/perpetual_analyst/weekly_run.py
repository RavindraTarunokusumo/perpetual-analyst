"""Weekly compaction orchestrator. Entry point: python -m perpetual_analyst.weekly_run"""

from __future__ import annotations

import argparse
import logging
import os

from dotenv import load_dotenv

from perpetual_analyst.analyst.agent import make_client
from perpetual_analyst.analyst.compaction import (
    apply_weekly_review,
    expire_observations,
    run_weekly_review,
)
from perpetual_analyst.analyst.theses import get_stale_theses
from perpetual_analyst.config import load_settings
from perpetual_analyst.store.db import init_db
from perpetual_analyst.store.models import Topic

load_dotenv()

logger = logging.getLogger(__name__)


def main(dry_run: bool = False, topic_slug: str | None = None) -> None:
    """Run the weekly memory-compaction pass."""
    db_path = os.environ.get("ANALYST_DB_PATH", "data/analyst.db")
    conn = init_db(db_path)
    settings = load_settings()

    client = None if dry_run else make_client()

    if topic_slug:
        row = conn.execute("SELECT * FROM topics WHERE slug = ?", (topic_slug,)).fetchone()
        topics: list[Topic] = [Topic.from_row(row)] if row else []
    else:
        rows = conn.execute("SELECT * FROM topics WHERE active = 1").fetchall()
        topics = [Topic.from_row(r) for r in rows]

    if not topics:
        print("[weekly_run] No active topics — nothing to do.")
        return

    successes = 0
    failures = 0

    for topic in topics:
        try:
            expired = expire_observations(conn, topic.id)
            print(f"[weekly_run] topic={topic.slug} expired={expired}")

            stale = get_stale_theses(topic.id, conn)
            if stale:
                print(f"[weekly_run] topic={topic.slug} stale_theses={[t.id for t in stale]}")

            output = run_weekly_review(topic, conn, client, settings, dry_run=dry_run)

            if output is not None:
                apply_weekly_review(topic.id, output, conn)

            successes += 1
        except Exception:
            logger.exception("[weekly_run] topic=%s failed", topic.slug)
            failures += 1

    print(f"[weekly_run] done — topics={len(topics)} successes={successes} failures={failures}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the weekly compaction pass")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts, skip API calls")
    parser.add_argument("--topic", default=None, help="Run for a single topic slug")
    args = parser.parse_args()
    main(dry_run=args.dry_run, topic_slug=args.topic)
