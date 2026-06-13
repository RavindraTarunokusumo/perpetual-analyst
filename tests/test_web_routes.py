def test_today_route_renders_latest_report(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"New report" in resp.data
    assert b"perpetual-analyst" in resp.data


def test_today_route_empty_state(empty_client):
    resp = empty_client.get("/")
    assert resp.status_code == 200
    assert b"No report yet" in resp.data
