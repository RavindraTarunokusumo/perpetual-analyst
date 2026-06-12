from __future__ import annotations

import pytest

from perpetual_analyst.config import SourceConfig, TopicConfig, sync_config


def _topic(slug="ai-labs", name="AI Labs", brief="Track the labs"):
    return TopicConfig(slug=slug, name=name, brief=brief)


def _source(name="Feed A", url="https://a.example/feed", topics=("ai-labs",)):
    return SourceConfig(name=name, type="rss", url=url, topics=list(topics))


def test_sync_inserts_topic_and_source_with_link(db):
    sync_config(db, [_topic()], [_source()])
    topic = db.execute("SELECT * FROM topics WHERE slug = 'ai-labs'").fetchone()
    assert topic["name"] == "AI Labs"
    source = db.execute("SELECT * FROM sources WHERE url = 'https://a.example/feed'").fetchone()
    assert source["type"] == "rss"
    link = db.execute(
        "SELECT * FROM topic_sources WHERE topic_id = ? AND source_id = ?",
        (topic["id"], source["id"]),
    ).fetchone()
    assert link is not None


def test_sync_is_idempotent(db):
    sync_config(db, [_topic()], [_source()])
    sync_config(db, [_topic()], [_source()])
    assert db.execute("SELECT COUNT(*) FROM topics WHERE slug='ai-labs'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM topic_sources").fetchone()[0] == 1


def test_sync_updates_definition_columns(db):
    sync_config(db, [_topic()], [_source()])
    sync_config(db, [_topic(name="AI Frontier Labs", brief="New brief")], [_source()])
    topic = db.execute("SELECT * FROM topics WHERE slug = 'ai-labs'").fetchone()
    assert topic["name"] == "AI Frontier Labs"
    assert topic["brief"] == "New brief"


def test_sync_preserves_runtime_columns(db):
    sync_config(db, [_topic()], [_source()])
    db.execute("UPDATE sources SET last_fetched_at = '2026-06-01 00:00:00', fetch_error_count = 3")
    db.commit()
    sync_config(db, [_topic()], [_source()])
    source = db.execute("SELECT * FROM sources").fetchone()
    assert source["last_fetched_at"] == "2026-06-01 00:00:00"
    assert source["fetch_error_count"] == 3


def test_sync_deactivates_removed_rows(db):
    sync_config(db, [_topic(), _topic(slug="old", name="Old")], [_source()])
    sync_config(db, [_topic()], [])
    old = db.execute("SELECT active FROM topics WHERE slug = 'old'").fetchone()
    assert old["active"] == 0
    source = db.execute("SELECT active FROM sources").fetchone()
    assert source["active"] == 0


def test_sync_leaves_inbox_sources_alone(db, sample_source):
    # sample_source fixture is type='inbox' with no YAML entry
    sync_config(db, [_topic()], [_source()])
    inbox = db.execute("SELECT active FROM sources WHERE id = ?", (sample_source,)).fetchone()
    assert inbox["active"] == 1


def test_sync_unknown_topic_slug_raises(db):
    with pytest.raises(ValueError, match="unknown topic"):
        sync_config(db, [], [_source(topics=("nope",))])
