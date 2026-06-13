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
    assert rows[0]["slug"] == "ai-labs"
    assert rows[0]["active_theses"] == 1  # the retired thesis is excluded


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
    assert [u["confidence_after"] for u in detail["updates"]] == [0.50, 0.62]


def test_thesis_detail_missing(seeded_conn):
    assert queries.thesis_detail(seeded_conn, 999) is None
