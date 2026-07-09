from perpetual_analyst.web import queries


def test_report_list_orders_desc_and_flags_undelivered(seeded_conn):
    rows = queries.report_list(seeded_conn)
    assert [r["report_date"] for r in rows] == ["2026-06-13", "2026-06-12"]
    assert rows[0]["delivered_at"] is None
    assert rows[1]["delivered_at"] is not None


def test_report_by_date_returns_markdown(seeded_conn):
    row = queries.report_by_date(seeded_conn, "2026-06-12")
    assert row["full_markdown"] == "# Old report"
    assert queries.report_by_date(seeded_conn, "1999-01-01") is None


def test_topic_list(seeded_conn):
    rows = queries.topic_list(seeded_conn)
    assert len(rows) == 1
    row = rows[0]
    assert row["slug"] == "ai-labs"
    assert row["active_theses"] == 1  # the retired thesis is excluded
    assert row["top_thesis"] == "Open-weight reaches parity"
    assert row["top_confidence"] == 0.62
    assert row["dossier_updated_at"] == "2026-06-12 09:00:00"
    assert row["updates_today"] == 0

    seeded_conn.execute(
        "INSERT INTO thesis_updates (id, thesis_id, change, confidence_before, "
        "confidence_after, triggered_by_item_id, created_at) "
        "VALUES (99, 1, 'today bump', 0.68, 0.70, 1, datetime('now'))"
    )
    seeded_conn.commit()
    rows = queries.topic_list(seeded_conn)
    assert rows[0]["updates_today"] == 1


def test_topic_detail_bundles_memory(seeded_conn):
    detail = queries.topic_detail(seeded_conn, "ai-labs")
    assert detail["topic"]["name"] == "AI Frontier Labs"
    assert detail["dossier"]["content"].startswith("## State of play")
    assert [t["id"] for t in detail["theses"]] == [1]  # active only
    assert detail["theses"][0]["confidence"] == 0.62
    assert detail["observations"][0]["kind"] == "signal"
    assert {i["id"] for i in detail["items"]} == {1, 2, 3}  # all topic-source items


def test_topic_detail_missing(seeded_conn):
    assert queries.topic_detail(seeded_conn, "nope") is None


def test_thesis_detail_includes_update_history(seeded_conn):
    detail = queries.thesis_detail(seeded_conn, 1)
    assert detail["thesis"]["statement"] == "Open-weight reaches parity"
    assert [u["confidence_after"] for u in detail["updates"]] == [0.50, 0.62, 0.68]


def test_thesis_detail_missing(seeded_conn):
    assert queries.thesis_detail(seeded_conn, 999) is None


def test_items_feed_unfiltered(seeded_conn):
    rows = queries.items_feed(seeded_conn)
    assert {r["id"] for r in rows} == {1, 2, 3}
    assert rows[0]["source_name"]  # joined source name present


def test_items_feed_filter_by_status(seeded_conn):
    rows = queries.items_feed(seeded_conn, status="skipped")
    assert {r["id"] for r in rows} == {2}


def test_items_feed_filter_by_source(seeded_conn):
    rows = queries.items_feed(seeded_conn, source_id=2)
    assert {r["id"] for r in rows} == {3}


def test_ops_overview(seeded_conn):
    ov = queries.ops_overview(seeded_conn)
    assert any(s["name"] == "arXiv cs.LG" for s in ov["sources"])
    assert ov["status_counts"]["analyzed"] == 1
    assert ov["status_counts"]["skipped"] == 1
    assert ov["status_counts"]["new"] == 1
    assert ov["undelivered"] == 1
    assert {s["id"] for s in ov["inbox_sources"]} == {2}


def test_all_dossiers(seeded_conn):
    rows = queries.all_dossiers(seeded_conn)
    assert len(rows) == 1
    assert rows[0]["slug"] == "ai-labs"
    assert rows[0]["content"].startswith("## State of play")


def test_today_changes_returns_seeded_delta(seeded_conn):
    rows = queries.today_changes(seeded_conn, "2026-06-13")
    assert len(rows) == 1
    topic = rows[0]
    assert topic["slug"] == "ai-labs"
    assert topic["quiet"] is False
    assert len(topic["deltas"]) == 1
    assert topic["deltas"][0]["before"] == 0.62
    assert topic["deltas"][0]["after"] == 0.68
    assert topic["deltas"][0]["statement"] == "Open-weight reaches parity"


def test_today_changes_quiet_when_no_updates(seeded_conn):
    rows = queries.today_changes(seeded_conn, "1999-01-01")
    assert len(rows) == 1
    assert rows[0]["quiet"] is True
    assert rows[0]["deltas"] == []
    assert rows[0]["new_observations"] == 0


def test_confidence_points_empty_updates():
    assert queries.confidence_points([]) == ""


def test_confidence_points_single_step():
    updates = [{"confidence_before": 0.5, "confidence_after": 0.62}]
    points = queries.confidence_points(updates)
    pairs = [tuple(map(float, p.split(","))) for p in points.split()]
    assert len(pairs) == 4
    assert pairs[0][1] == pairs[1][1]  # horizontal hold before step
    assert pairs[2][1] == pairs[3][1]  # horizontal hold after step
    assert pairs[1][0] == pairs[2][0]  # vertical step at same x


def test_confidence_points_skips_none_confidences():
    updates = [
        {"confidence_before": None, "confidence_after": 0.5},
        {"confidence_before": 0.5, "confidence_after": 0.62},
    ]
    points = queries.confidence_points(updates)
    assert points != ""


def test_confidence_points_all_none_returns_empty():
    updates = [{"confidence_before": None, "confidence_after": None}]
    assert queries.confidence_points(updates) == ""


def test_confidence_points_y_inverts_confidence():
    updates = [{"confidence_before": 1.0, "confidence_after": 0.0}]
    points = queries.confidence_points(updates)
    pairs = [tuple(map(float, p.split(","))) for p in points.split()]
    assert pairs[0][1] == 6.0  # confidence 1.0 → top (pad)
    assert pairs[-1][1] == 90.0  # confidence 0.0 → bottom
