"""Live end-to-end smoke test: real feeds, real triage, one real analyst run.

Run explicitly: pytest -m smoke
Requires OPENROUTER_API_KEY in .env and network access. Costs ~cents
(triage on deepseek-flash) plus one analyst call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from perpetual_analyst.analyst.agent import make_client, run_topic
from perpetual_analyst.analyst.triage import SKIP_THRESHOLD, triage_items
from perpetual_analyst.config import load_settings, load_sources, load_topics, sync_config
from perpetual_analyst.ingestion.rss import fetch_rss
from perpetual_analyst.store.db import init_db
from perpetual_analyst.store.models import Item, Source, Topic

SMOKE_DB = "data/smoke-phase2.db"
MAX_ANALYST_ITEMS = 10


@pytest.mark.smoke
def test_full_pipeline_live():
    Path(SMOKE_DB).unlink(missing_ok=True)
    conn = init_db(SMOKE_DB)
    sync_config(conn, load_topics(), load_sources())

    topic_row = conn.execute("SELECT * FROM topics WHERE active = 1 LIMIT 1").fetchone()
    assert topic_row, "no active topic in config/topics.yaml"
    topic = Topic.from_row(topic_row)

    sources = [
        Source.from_row(r)
        for r in conn.execute(
            "SELECT s.* FROM sources s JOIN topic_sources ts ON ts.source_id = s.id"
            " WHERE ts.topic_id = ? AND s.type = 'rss' AND s.active = 1",
            (topic.id,),
        ).fetchall()
    ]
    assert sources, "no active rss sources linked to topic"

    total = sum(fetch_rss(source, conn) for source in sources)
    assert total > 0, "no items fetched from live feeds"

    items = [
        Item.from_row(r)
        for r in conn.execute("SELECT * FROM items WHERE status = 'new'").fetchall()
    ]
    settings = load_settings()
    client = make_client()
    results = triage_items(items, topic.brief or "", client, settings, conn)
    assert results, "triage returned no validated results"

    keep = [
        Item.from_row(r)
        for r in conn.execute(
            "SELECT * FROM items WHERE status = 'new' AND triage_score >= ?"
            " ORDER BY triage_score DESC LIMIT ?",
            (SKIP_THRESHOLD, MAX_ANALYST_ITEMS),
        ).fetchall()
    ]
    assert keep, "triage skipped everything - check the topic brief or feeds"

    analysis = run_topic(topic, keep, conn, client, settings)
    assert analysis is not None
    assert analysis.report_section_markdown or analysis.nothing_significant
    if analysis.new_observations:
        obs_count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        assert obs_count == len(analysis.new_observations)
    conn.close()
