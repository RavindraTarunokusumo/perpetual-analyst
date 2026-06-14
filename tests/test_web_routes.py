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


def test_reading_route_lists_dossiers(client):
    resp = client.get("/reading")
    assert resp.status_code == 200
    assert b"State of play" in resp.data


def test_reading_toggle_sets_cookie_and_redirects_home(client):
    resp = client.post("/reading/toggle")
    assert resp.status_code == 302
    assert "reading=1" in resp.headers.get("Set-Cookie", "")


def test_home_redirects_to_reading_when_cookie_set(client):
    client.set_cookie("reading", "1")
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/reading")


def test_thesis_route_wrong_slug_404(client):
    # thesis 1 belongs to ai-labs; a mismatched slug must not render it
    assert client.get("/topics/not-ai-labs/thesis/1").status_code == 404


def test_inbox_post_redirects_and_inserts(client):
    resp = client.post("/actions/inbox", data={"topic_id": "1", "text": "via the web"})
    assert resp.status_code == 302
    follow = client.get("/items")
    assert b"via the web" in follow.data


def test_retry_route_redirects(client, monkeypatch):
    from perpetual_analyst.web import actions

    monkeypatch.setattr(actions, "retry_undelivered", lambda conn: 1)
    resp = client.post("/actions/retry")
    assert resp.status_code == 302


def test_run_status_endpoint(client):
    resp = client.get("/actions/run/status")
    assert resp.status_code == 200
    assert resp.json["state"] in {"idle", "running", "done", "error"}


def test_cli_web_command_registered():
    from typer.testing import CliRunner

    from perpetual_analyst.cli import app

    result = CliRunner().invoke(app, ["web", "--help"])
    assert result.exit_code == 0
    assert "host" in result.output.lower()
