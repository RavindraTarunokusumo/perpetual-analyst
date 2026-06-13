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
