from __future__ import annotations

import pytest

from perpetual_analyst.retrieval.search import related_items, related_observations


def _obs(db, topic_id: int, content: str, days_ago: int = 0, status: str = "active"):
    db.execute(
        f"""INSERT INTO observations (topic_id, kind, content, importance, status, created_at)
            VALUES (?, 'fact', ?, 2, ?, datetime('now', '-{days_ago} days'))""",
        (topic_id, content, status),
    )
    db.commit()


def _item(db, source_id: int, title: str, text: str, days_ago: int = 0, status: str = "new"):
    cur = db.execute(
        f"""INSERT INTO items (source_id, content_hash, title, raw_text, status, fetched_at)
            VALUES (?, ?, ?, ?, ?, datetime('now', '-{days_ago} days'))""",
        (source_id, f"hash_{title}", title, text, status),
    )
    db.commit()
    return cur.lastrowid


@pytest.fixture
def linked_source(db, sample_topic, sample_source):
    db.execute(
        "INSERT INTO topic_sources (topic_id, source_id) VALUES (?, ?)",
        (sample_topic.id, sample_source),
    )
    db.commit()
    return sample_source


def test_related_observations_matches_keywords(db, sample_topic):
    _obs(db, sample_topic.id, "GPU export controls tightened in May")
    _obs(db, sample_topic.id, "New cafeteria menu announced")
    results = related_observations("export controls on GPUs", sample_topic.id, db)
    assert [o.content for o in results] == ["GPU export controls tightened in May"]


def test_related_observations_excludes_other_topics(db, sample_topic):
    db.execute("INSERT INTO topics (user_id, slug, name) VALUES (1, 'other', 'Other')")
    other_id = db.execute("SELECT id FROM topics WHERE slug = 'other'").fetchone()["id"]
    _obs(db, other_id, "GPU export controls tightened")
    assert related_observations("GPU export controls", sample_topic.id, db) == []


def test_related_observations_excludes_inactive(db, sample_topic):
    _obs(db, sample_topic.id, "GPU export controls tightened", status="expired")
    assert related_observations("GPU export controls", sample_topic.id, db) == []


def test_recent_observation_ranks_first(db, sample_topic):
    _obs(db, sample_topic.id, "Compute scaling continues unabated", days_ago=60)
    _obs(db, sample_topic.id, "Compute scaling shows new datapoint", days_ago=1)
    # both rows tie on bm25 for the matched terms; the ×1.5 recency boost must break the tie
    results = related_observations("compute scaling", sample_topic.id, db, k=2)
    assert len(results) == 2
    assert "new datapoint" in results[0].content


def test_related_observations_k_limit(db, sample_topic):
    for i in range(8):
        _obs(db, sample_topic.id, f"Compute trend number {i}")
    assert len(related_observations("compute trend", sample_topic.id, db, k=5)) == 5


def test_hostile_query_text_does_not_raise(db, sample_topic):
    _obs(db, sample_topic.id, "Anything at all")
    related_observations('AND "NEAR( OR *', sample_topic.id, db)
    related_observations("", sample_topic.id, db)


def test_related_items_joins_topic_and_excludes(db, sample_topic, linked_source):
    matching = _item(db, linked_source, "GPU Export Rules", "Export controls on GPUs expand")
    _item(db, linked_source, "Cooking Tips", "How to roast vegetables")
    skipped = _item(
        db, linked_source, "GPU Export Skipped", "Export controls skipped", status="skipped"
    )
    results = related_items("GPU export controls", sample_topic.id, db)
    ids = [i.id for i in results]
    assert matching in ids
    assert skipped not in ids


def test_related_items_excludes_current_batch(db, sample_topic, linked_source):
    current = _item(db, linked_source, "GPU Export Today", "Export controls on GPUs today")
    prior = _item(db, linked_source, "GPU Export Last Week", "Export controls on GPUs before")
    results = related_items("GPU export controls", sample_topic.id, db, exclude_ids=[current])
    ids = [i.id for i in results]
    assert prior in ids
    assert current not in ids


def test_exclude_ids_rejects_non_ints(db, sample_topic, linked_source):
    with pytest.raises(TypeError, match="exclude_ids"):
        related_items("anything", sample_topic.id, db, exclude_ids=[None])
