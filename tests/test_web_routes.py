def test_today_route_renders_latest_report(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"New report" in resp.data
    assert b"perpetual-analyst" in resp.data


def test_today_route_empty_state(empty_client):
    resp = empty_client.get("/")
    assert resp.status_code == 200
    assert b"No report yet" in resp.data


def test_reports_list_route(client):
    resp = client.get("/reports")
    assert resp.status_code == 200
    assert b"2026-06-13" in resp.data
    assert b"2026-06-12" in resp.data


def test_report_detail_route(client):
    resp = client.get("/reports/2026-06-12")
    assert resp.status_code == 200
    assert b"Old report" in resp.data


def test_report_detail_missing_returns_404(client):
    assert client.get("/reports/1999-01-01").status_code == 404


def test_reports_empty_state(empty_client):
    resp = empty_client.get("/reports")
    assert resp.status_code == 200
    assert b"No reports yet" in resp.data


def test_topics_route(client):
    resp = client.get("/topics")
    assert resp.status_code == 200
    assert b"AI Frontier Labs" in resp.data


def test_topic_detail_route(client):
    resp = client.get("/topics/ai-labs")
    assert resp.status_code == 200
    assert b"State of play" in resp.data
    assert b"Open-weight reaches parity" in resp.data


def test_topic_detail_404(client):
    assert client.get("/topics/nope").status_code == 404


def test_thesis_route(client):
    resp = client.get("/topics/ai-labs/thesis/1")
    assert resp.status_code == 200
    assert b"new MoE evidence" in resp.data


def test_topics_empty_state(empty_client):
    resp = empty_client.get("/topics")
    assert resp.status_code == 200
    assert b"No topics" in resp.data


def test_items_route(client):
    resp = client.get("/items")
    assert resp.status_code == 200
    assert b"Scaling laws" in resp.data


def test_items_route_status_filter(client):
    resp = client.get("/items?status=skipped")
    assert resp.status_code == 200
    assert b"Noise" in resp.data
    assert b"Scaling laws" not in resp.data


def test_ops_route(client):
    resp = client.get("/ops")
    assert resp.status_code == 200
    assert b"arXiv cs.LG" in resp.data


def test_items_empty_state(empty_client):
    resp = empty_client.get("/items")
    assert resp.status_code == 200
    assert b"No items" in resp.data
