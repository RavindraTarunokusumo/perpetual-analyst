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
