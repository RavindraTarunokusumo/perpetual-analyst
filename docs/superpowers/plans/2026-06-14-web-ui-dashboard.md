# Web UI Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local single-user Flask + Jinja dashboard over the existing `data/analyst.db` — unified reading, analyst-memory inspection, and ops, plus three light write actions.

**Architecture:** New `src/perpetual_analyst/web/` package. Thin Flask route handlers in `app.py` call read-only view-model builders in `queries.py` and write handlers in `actions.py`; both reuse existing `store/`, `report/`, `delivery/`, and `daily_run` code. Each request opens a short-lived SQLite connection (WAL already on); the background daily-run thread opens its own. Served by a new `analyst web` CLI command bound to `127.0.0.1`.

**Tech Stack:** Flask, Jinja2, `markdown` (report rendering), existing `sqlite3` store. Tests via Flask test client + pytest against a seeded temp-file DB.

**Spec:** `docs/superpowers/specs/2026-06-14-web-ui-dashboard-design.md`

**Deviation logged:** the add-inbox action accepts **text (required) + optional title/URL metadata**, not live URL fetching — fetching/extraction in a request is out of scope for V1; pasted text becomes the item's `raw_text` for next run's triage. (Narrows the spec's "URL or text".)

---

## File Structure

| File | Responsibility |
|---|---|
| `src/perpetual_analyst/web/__init__.py` | Package marker; exports `create_app`. |
| `src/perpetual_analyst/web/queries.py` | Read-only view-model builders — all SELECTs. |
| `src/perpetual_analyst/web/actions.py` | 3 write handlers + run lock/thread/status. |
| `src/perpetual_analyst/web/app.py` | `create_app(db_path)` factory + route handlers. |
| `src/perpetual_analyst/web/templates/*.html` | One Jinja template per page + `base.html`. |
| `src/perpetual_analyst/web/static/app.css` | One stylesheet. |
| `src/perpetual_analyst/cli.py` | Add `analyst web` command (modify). |
| `pyproject.toml` | Add `flask`, `markdown` deps (modify). |
| `tests/conftest.py` | Add seeded temp-DB fixtures (modify or create). |
| `tests/test_web_queries.py` | Unit tests for `queries.py`. |
| `tests/test_web_routes.py` | Route/render tests (read pages + reading mode). |
| `tests/test_web_actions.py` | Action tests (inbox/retry/run + lock). |

---

## Task 1: Scaffold package, dependencies, and app factory

**Files:**
- Modify: `pyproject.toml` (dependencies)
- Create: `src/perpetual_analyst/web/__init__.py`
- Create: `src/perpetual_analyst/web/app.py`
- Create: `src/perpetual_analyst/web/templates/base.html`
- Create: `src/perpetual_analyst/web/templates/today.html`
- Create: `src/perpetual_analyst/web/static/app.css`
- Create: `tests/conftest.py` (add fixtures; file already exists — append)
- Create: `tests/test_web_routes.py`

- [ ] **Step 1: Add dependencies and install editable**

In `pyproject.toml`, add to the `[project] dependencies` list:
```toml
  "flask>=3.0",
  "markdown>=3.5",
```
Then run:
```bash
pip install -e .
```
Expected: installs flask + markdown; `python -c "import flask, markdown"` exits 0.

- [ ] **Step 2: Add the seeded DB fixtures to `tests/conftest.py`**

Append (keep existing content):
```python
import sqlite3

import pytest

from perpetual_analyst.store.db import init_db


def _seed(path: str) -> None:
    conn = init_db(path)
    conn.execute("INSERT INTO users (id, telegram_chat_id) VALUES (1, '999')")
    conn.execute(
        "INSERT INTO topics (id, user_id, slug, name, brief, active) "
        "VALUES (1, 1, 'ai-labs', 'AI Frontier Labs', 'frontier model labs', 1)"
    )
    conn.execute(
        "INSERT INTO sources (id, type, url, name, active, last_fetched_at, fetch_error_count) "
        "VALUES (1, 'rss', 'http://x/feed', 'arXiv cs.LG', 1, '2026-06-13 10:00:00', 0)"
    )
    conn.execute(
        "INSERT INTO sources (id, type, url, name, active, fetch_error_count) "
        "VALUES (2, 'inbox', NULL, 'inbox', 1, 0)"
    )
    conn.execute("INSERT INTO topic_sources (topic_id, source_id) VALUES (1, 1), (1, 2)")
    conn.execute(
        "INSERT INTO items (id, source_id, url, content_hash, title, raw_text, "
        "triage_summary, triage_score, status) VALUES "
        "(1, 1, 'http://x/1', 'h1', 'Scaling laws', 'body one', 'a summary', 0.81, 'analyzed')"
    )
    conn.execute(
        "INSERT INTO items (id, source_id, url, content_hash, title, raw_text, "
        "triage_summary, triage_score, status) VALUES "
        "(2, 1, 'http://x/2', 'h2', 'Noise', 'body two', 'low signal', 0.12, 'skipped')"
    )
    conn.execute(
        "INSERT INTO items (id, source_id, content_hash, title, raw_text, status) "
        "VALUES (3, 2, 'h3', 'Pasted note', 'pasted body', 'new')"
    )
    conn.execute(
        "INSERT INTO dossiers (topic_id, content, updated_at) "
        "VALUES (1, '## State of play\nThe frontier is consolidating.', '2026-06-12 09:00:00')"
    )
    conn.execute(
        "INSERT INTO theses (id, topic_id, statement, rationale, confidence, status, "
        "created_at, updated_at) VALUES "
        "(1, 1, 'Open-weight reaches parity', 'why it holds', 0.62, 'active', "
        "'2026-06-01 00:00:00', '2026-06-12 00:00:00')"
    )
    conn.execute(
        "INSERT INTO theses (id, topic_id, statement, rationale, confidence, status) "
        "VALUES (2, 1, 'Retired idea', 'old', 0.30, 'retired')"
    )
    conn.execute(
        "INSERT INTO thesis_updates (id, thesis_id, change, confidence_before, "
        "confidence_after, triggered_by_item_id, created_at) VALUES "
        "(1, 1, 'initial position', NULL, 0.50, NULL, '2026-06-01 00:00:00')"
    )
    conn.execute(
        "INSERT INTO thesis_updates (id, thesis_id, change, confidence_before, "
        "confidence_after, triggered_by_item_id, created_at) VALUES "
        "(2, 1, 'new MoE evidence', 0.50, 0.62, 1, '2026-06-12 00:00:00')"
    )
    conn.execute(
        "INSERT INTO observations (id, topic_id, kind, content, importance, "
        "source_item_ids, status, created_at) VALUES "
        "(1, 1, 'signal', 'New MoE checkpoint released', 3, '[1]', 'active', '2026-06-12 00:00:00')"
    )
    conn.execute(
        "INSERT INTO reports (id, user_id, report_date, digest_text, full_markdown, delivered_at) "
        "VALUES (1, 1, '2026-06-12', 'old digest', '# Old report', '2026-06-12 12:00:00')"
    )
    conn.execute(
        "INSERT INTO reports (id, user_id, report_date, digest_text, full_markdown, delivered_at) "
        "VALUES (2, 1, '2026-06-13', 'new digest', "
        "'# New report\n\nFinding cited [item:1] here.', NULL)"
    )
    conn.commit()
    conn.close()


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "seeded.db")
    _seed(path)
    return path


@pytest.fixture
def empty_db_path(tmp_path):
    path = str(tmp_path / "empty.db")
    init_db(path).close()
    return path


@pytest.fixture
def seeded_conn(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


@pytest.fixture
def client(db_path):
    from perpetual_analyst.web.app import create_app

    app = create_app(db_path)
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture
def empty_client(empty_db_path):
    from perpetual_analyst.web.app import create_app

    app = create_app(empty_db_path)
    app.config.update(TESTING=True)
    return app.test_client()
```

- [ ] **Step 3: Write the failing route test**

Create `tests/test_web_routes.py`:
```python
def test_today_route_renders_latest_report(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"New report" in resp.data  # rendered markdown from latest report
    assert b"perpetual-analyst" in resp.data  # nav from base.html


def test_today_route_empty_state(empty_client):
    resp = empty_client.get("/")
    assert resp.status_code == 200
    assert b"No report yet" in resp.data
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `pytest tests/test_web_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: perpetual_analyst.web.app` (no app yet).

- [ ] **Step 5: Create the package and app factory**

Create `src/perpetual_analyst/web/__init__.py`:
```python
from perpetual_analyst.web.app import create_app

__all__ = ["create_app"]
```

Create `src/perpetual_analyst/web/app.py`:
```python
"""Flask app factory for the local single-user dashboard. Binds loopback only."""

from __future__ import annotations

import sqlite3

import markdown as md
from flask import Flask, g, render_template

from perpetual_analyst.report.render import render_citations
from perpetual_analyst.web import queries


def create_app(db_path: str) -> Flask:
    app = Flask(__name__)
    # Local single-user tool: this key only signs flash cookies, guards nothing.
    app.secret_key = "perpetual-analyst-local-ui"
    app.config["DB_PATH"] = db_path

    def get_conn() -> sqlite3.Connection:
        if "conn" not in g:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            g.conn = conn
        return g.conn

    @app.teardown_appcontext
    def _close_conn(_exc: object) -> None:
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    def render_report_html(full_markdown: str | None) -> str:
        if not full_markdown:
            return ""
        # render_citations is a no-op when no [item:N] tags remain (idempotent).
        text = render_citations(full_markdown, get_conn())
        return md.markdown(text, extensions=["fenced_code", "tables", "footnotes"])

    @app.route("/")
    def today():
        report = queries.latest_report(get_conn())
        report_html = render_report_html(report["full_markdown"]) if report else ""
        return render_template("today.html", report=report, report_html=report_html)

    return app
```

Create `src/perpetual_analyst/web/queries.py`:
```python
"""Read-only view-model builders. All dashboard SELECTs live here."""

from __future__ import annotations

import sqlite3


def latest_report(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        "SELECT * FROM reports ORDER BY report_date DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None
```

- [ ] **Step 6: Create `base.html`, `today.html`, and `app.css`**

Create `src/perpetual_analyst/web/templates/base.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}perpetual-analyst{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='app.css') }}">
</head>
<body>
  <nav class="nav">
    <span class="brand">perpetual-analyst</span>
    <a href="{{ url_for('today') }}">Today</a>
    {% block nav_extra %}{% endblock %}
  </nav>
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for category, message in messages %}
      <div class="flash flash-{{ category }}">{{ message }}</div>
    {% endfor %}
  {% endwith %}
  <main class="main">{% block content %}{% endblock %}</main>
</body>
</html>
```

Create `src/perpetual_analyst/web/templates/today.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>Today</h1>
{% if report %}
  <p class="meta">{{ report.report_date }}{% if not report.delivered_at %} · <span class="warn">undelivered</span>{% endif %}</p>
  <article class="report">{{ report_html|safe }}</article>
{% else %}
  <p class="empty">No report yet — run the pipeline from Ops.</p>
{% endif %}
{% endblock %}
```

Create `src/perpetual_analyst/web/static/app.css`:
```css
:root { --fg: #1d2127; --muted: #6b7280; --line: #e5e7eb; --accent: #2f5fa8; --warn: #b45309; }
* { box-sizing: border-box; }
body { margin: 0; font: 15px/1.6 system-ui, sans-serif; color: var(--fg); }
.nav { display: flex; gap: 16px; align-items: center; padding: 10px 20px;
  border-bottom: 1px solid var(--line); position: sticky; top: 0; background: #fff; }
.nav a { color: var(--accent); text-decoration: none; }
.nav a.active { font-weight: 600; text-decoration: underline; }
.nav .brand { font-weight: 700; margin-right: 8px; }
.nav .spacer { flex: 1; }
.main { max-width: 920px; margin: 0 auto; padding: 24px 20px; }
.meta, .empty, .muted { color: var(--muted); }
.warn { color: var(--warn); }
.report { max-width: 720px; }
.flash { padding: 8px 20px; background: #eef2ff; border-bottom: 1px solid var(--line); }
.flash-error { background: #fef2f2; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--line); }
.bar { display: inline-block; height: 8px; background: var(--accent); border-radius: 4px; vertical-align: middle; }
.bar-track { display: inline-block; width: 90px; height: 8px; background: var(--line); border-radius: 4px; }
.card { border: 1px solid var(--line); border-radius: 8px; padding: 14px; margin-bottom: 14px; }
.label { text-transform: uppercase; font-size: 11px; letter-spacing: .04em; color: var(--muted); }
form.inline { display: inline; }
.btn { font: inherit; padding: 5px 12px; border: 1px solid var(--accent); background: var(--accent);
  color: #fff; border-radius: 6px; cursor: pointer; }
.btn:disabled { background: var(--muted); border-color: var(--muted); cursor: not-allowed; }
.reading article { max-width: 680px; margin: 0 auto 28px; }
```

- [ ] **Step 7: Run the route test to verify it passes**

Run: `pytest tests/test_web_routes.py -v`
Expected: PASS (both tests).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/perpetual_analyst/web/__init__.py src/perpetual_analyst/web/app.py src/perpetual_analyst/web/queries.py src/perpetual_analyst/web/templates/base.html src/perpetual_analyst/web/templates/today.html src/perpetual_analyst/web/static/app.css tests/conftest.py tests/test_web_routes.py
git commit -m "feat(web): scaffold Flask dashboard with Today page"
```

---

## Task 2: Reports archive + report detail

**Files:**
- Modify: `src/perpetual_analyst/web/queries.py`
- Modify: `src/perpetual_analyst/web/app.py`
- Create: `src/perpetual_analyst/web/templates/reports.html`
- Create: `src/perpetual_analyst/web/templates/report_detail.html`
- Modify: `tests/test_web_queries.py` (create)
- Modify: `tests/test_web_routes.py`

- [ ] **Step 1: Write failing query tests**

Create `tests/test_web_queries.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_web_queries.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'report_list'`.

- [ ] **Step 3: Add query functions**

Append to `src/perpetual_analyst/web/queries.py`:
```python
def report_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, report_date, delivered_at, created_at "
        "FROM reports ORDER BY report_date DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def report_by_date(conn: sqlite3.Connection, report_date: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM reports WHERE report_date = ?", (report_date,)
    ).fetchone()
    return dict(row) if row else None
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_web_queries.py -v`
Expected: PASS.

- [ ] **Step 5: Write failing route tests**

Append to `tests/test_web_routes.py`:
```python
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
```

- [ ] **Step 6: Run to verify failure**

Run: `pytest tests/test_web_routes.py -k report -v`
Expected: FAIL — 404 for `/reports` (route missing).

- [ ] **Step 7: Add routes and templates**

In `src/perpetual_analyst/web/app.py`, add inside `create_app` (after the `today` route), and import `abort`:
```python
from flask import Flask, abort, g, render_template
```
```python
    @app.route("/reports")
    def reports():
        return render_template("reports.html", reports=queries.report_list(get_conn()))

    @app.route("/reports/<report_date>")
    def report_detail(report_date: str):
        report = queries.report_by_date(get_conn(), report_date)
        if report is None:
            abort(404)
        report_html = render_report_html(report["full_markdown"])
        return render_template("report_detail.html", report=report, report_html=report_html)
```

Add a nav link in `base.html` after the Today link:
```html
    <a href="{{ url_for('reports') }}">Reports</a>
```

Create `src/perpetual_analyst/web/templates/reports.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>Reports</h1>
{% if reports %}
<table>
  <tr><th>Date</th><th>Delivered</th></tr>
  {% for r in reports %}
  <tr>
    <td><a href="{{ url_for('report_detail', report_date=r.report_date) }}">{{ r.report_date }}</a></td>
    <td>{% if r.delivered_at %}{{ r.delivered_at }}{% else %}<span class="warn">undelivered</span>{% endif %}</td>
  </tr>
  {% endfor %}
</table>
{% else %}
<p class="empty">No reports yet — run the pipeline from Ops.</p>
{% endif %}
{% endblock %}
```

Create `src/perpetual_analyst/web/templates/report_detail.html`:
```html
{% extends "base.html" %}
{% block content %}
<p class="meta"><a href="{{ url_for('reports') }}">← Reports</a></p>
<h1>{{ report.report_date }}</h1>
<article class="report">{{ report_html|safe }}</article>
{% endblock %}
```

- [ ] **Step 8: Run to verify pass**

Run: `pytest tests/test_web_routes.py tests/test_web_queries.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/perpetual_analyst/web/queries.py src/perpetual_analyst/web/app.py src/perpetual_analyst/web/templates/reports.html src/perpetual_analyst/web/templates/report_detail.html src/perpetual_analyst/web/templates/base.html tests/test_web_queries.py tests/test_web_routes.py
git commit -m "feat(web): reports archive and detail pages"
```

---

## Task 3: Topics list, topic detail, thesis detail

**Files:**
- Modify: `src/perpetual_analyst/web/queries.py`
- Modify: `src/perpetual_analyst/web/app.py`
- Create: `src/perpetual_analyst/web/templates/topics.html`
- Create: `src/perpetual_analyst/web/templates/topic.html`
- Create: `src/perpetual_analyst/web/templates/thesis.html`
- Modify: `tests/test_web_queries.py`, `tests/test_web_routes.py`

- [ ] **Step 1: Write failing query tests**

Append to `tests/test_web_queries.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_web_queries.py -k "topic or thesis" -v`
Expected: FAIL — functions undefined.

- [ ] **Step 3: Add query functions**

Append to `src/perpetual_analyst/web/queries.py`:
```python
def topic_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT t.id, t.slug, t.name, t.brief,
                  (SELECT COUNT(*) FROM theses
                   WHERE topic_id = t.id AND status = 'active') AS active_theses
           FROM topics t WHERE t.active = 1 ORDER BY t.name"""
    ).fetchall()
    return [dict(r) for r in rows]


def topic_detail(conn: sqlite3.Connection, slug: str) -> dict | None:
    topic = conn.execute("SELECT * FROM topics WHERE slug = ?", (slug,)).fetchone()
    if topic is None:
        return None
    topic_id = topic["id"]
    dossier = conn.execute(
        "SELECT * FROM dossiers WHERE topic_id = ?", (topic_id,)
    ).fetchone()
    theses = conn.execute(
        "SELECT * FROM theses WHERE topic_id = ? AND status = 'active' "
        "ORDER BY confidence DESC",
        (topic_id,),
    ).fetchall()
    observations = conn.execute(
        "SELECT * FROM observations WHERE topic_id = ? AND status != 'expired' "
        "ORDER BY importance DESC, created_at DESC LIMIT 20",
        (topic_id,),
    ).fetchall()
    items = conn.execute(
        """SELECT i.* FROM items i
           WHERE i.source_id IN (
               SELECT source_id FROM topic_sources WHERE topic_id = ?)
           ORDER BY i.fetched_at DESC LIMIT 20""",
        (topic_id,),
    ).fetchall()
    return {
        "topic": dict(topic),
        "dossier": dict(dossier) if dossier else None,
        "theses": [dict(r) for r in theses],
        "observations": [dict(r) for r in observations],
        "items": [dict(r) for r in items],
    }


def thesis_detail(conn: sqlite3.Connection, thesis_id: int) -> dict | None:
    thesis = conn.execute("SELECT * FROM theses WHERE id = ?", (thesis_id,)).fetchone()
    if thesis is None:
        return None
    updates = conn.execute(
        "SELECT * FROM thesis_updates WHERE thesis_id = ? ORDER BY created_at",
        (thesis_id,),
    ).fetchall()
    return {"thesis": dict(thesis), "updates": [dict(r) for r in updates]}
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_web_queries.py -k "topic or thesis" -v`
Expected: PASS.

- [ ] **Step 5: Write failing route tests**

Append to `tests/test_web_routes.py`:
```python
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
```

- [ ] **Step 6: Run to verify failure**

Run: `pytest tests/test_web_routes.py -k "topic or thesis" -v`
Expected: FAIL — routes missing (404).

- [ ] **Step 7: Add routes and templates**

In `app.py`, add routes inside `create_app`:
```python
    @app.route("/topics")
    def topics():
        return render_template("topics.html", topics=queries.topic_list(get_conn()))

    @app.route("/topics/<slug>")
    def topic(slug: str):
        detail = queries.topic_detail(get_conn(), slug)
        if detail is None:
            abort(404)
        return render_template("topic.html", **detail)

    @app.route("/topics/<slug>/thesis/<int:thesis_id>")
    def thesis(slug: str, thesis_id: int):
        detail = queries.thesis_detail(get_conn(), thesis_id)
        if detail is None:
            abort(404)
        return render_template("thesis.html", slug=slug, **detail)
```

Add nav link in `base.html` after Today:
```html
    <a href="{{ url_for('topics') }}">Topics</a>
```

Create `src/perpetual_analyst/web/templates/topics.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>Topics</h1>
{% if topics %}
<table>
  <tr><th>Topic</th><th>Active theses</th></tr>
  {% for t in topics %}
  <tr>
    <td><a href="{{ url_for('topic', slug=t.slug) }}">{{ t.name }}</a></td>
    <td>{{ t.active_theses }}</td>
  </tr>
  {% endfor %}
</table>
{% else %}
<p class="empty">No topics configured.</p>
{% endif %}
{% endblock %}
```

Create `src/perpetual_analyst/web/templates/topic.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>{{ topic.name }}</h1>
{% if dossier %}
<section class="card">
  <div class="label">Dossier · updated {{ dossier.updated_at or '—' }}</div>
  <pre class="muted" style="white-space:pre-wrap">{{ dossier.content }}</pre>
</section>
{% endif %}

<section class="card">
  <div class="label">Active theses ({{ theses|length }} / 7)</div>
  {% for t in theses %}
  <div>
    <a href="{{ url_for('thesis', slug=topic.slug, thesis_id=t.id) }}">{{ t.statement }}</a>
    — conf {{ '%.2f'|format(t.confidence or 0) }}
    <span class="bar-track"><span class="bar" style="width:{{ ((t.confidence or 0) * 90)|int }}px"></span></span>
  </div>
  {% else %}
  <p class="empty">No active theses.</p>
  {% endfor %}
</section>

<section class="card">
  <div class="label">Recent observations</div>
  {% for o in observations %}
  <div>● {{ o.kind }} — {{ o.content }} <span class="muted">imp {{ o.importance }} · {{ o.source_item_ids or '' }}</span></div>
  {% else %}
  <p class="empty">No observations.</p>
  {% endfor %}
</section>

<section class="card">
  <div class="label">Recent items</div>
  {% for i in items %}
  <div>{{ i.title or '(untitled)' }} <span class="muted">{{ '%.2f'|format(i.triage_score or 0) }} · {{ i.status }}</span></div>
  {% else %}
  <p class="empty">No items.</p>
  {% endfor %}
</section>
{% endblock %}
```

Create `src/perpetual_analyst/web/templates/thesis.html`:
```html
{% extends "base.html" %}
{% block content %}
<p class="meta"><a href="{{ url_for('topic', slug=slug) }}">← {{ slug }}</a></p>
<h1>{{ thesis.statement }}</h1>
<p>Status: {{ thesis.status }} · confidence {{ '%.2f'|format(thesis.confidence or 0) }}</p>
{% if thesis.rationale %}<p class="muted">{{ thesis.rationale }}</p>{% endif %}
<h2>Update history</h2>
<table>
  <tr><th>When</th><th>Before → After</th><th>Change</th></tr>
  {% for u in updates %}
  <tr>
    <td>{{ u.created_at }}</td>
    <td>{{ '%.2f'|format(u.confidence_before) if u.confidence_before is not none else '—' }}
        → {{ '%.2f'|format(u.confidence_after) if u.confidence_after is not none else '—' }}</td>
    <td>{{ u.change }}</td>
  </tr>
  {% endfor %}
</table>
{% endblock %}
```

- [ ] **Step 8: Run to verify pass**

Run: `pytest tests/test_web_routes.py tests/test_web_queries.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/perpetual_analyst/web/queries.py src/perpetual_analyst/web/app.py src/perpetual_analyst/web/templates/topics.html src/perpetual_analyst/web/templates/topic.html src/perpetual_analyst/web/templates/thesis.html src/perpetual_analyst/web/templates/base.html tests/test_web_queries.py tests/test_web_routes.py
git commit -m "feat(web): topics, topic detail, and thesis history pages"
```

---

## Task 4: Items feed (filterable) + Ops overview

**Files:**
- Modify: `src/perpetual_analyst/web/queries.py`
- Modify: `src/perpetual_analyst/web/app.py`
- Create: `src/perpetual_analyst/web/templates/items.html`
- Create: `src/perpetual_analyst/web/templates/ops.html`
- Modify: `tests/test_web_queries.py`, `tests/test_web_routes.py`

- [ ] **Step 1: Write failing query tests**

Append to `tests/test_web_queries.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_web_queries.py -k "items_feed or ops" -v`
Expected: FAIL — undefined.

- [ ] **Step 3: Add query functions**

Append to `src/perpetual_analyst/web/queries.py`:
```python
def items_feed(
    conn: sqlite3.Connection,
    status: str | None = None,
    source_id: int | None = None,
    limit: int = 100,
) -> list[dict]:
    clauses, params = [], []
    if status:
        clauses.append("i.status = ?")
        params.append(status)
    if source_id:
        clauses.append("i.source_id = ?")
        params.append(source_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    rows = conn.execute(
        f"""SELECT i.id, i.title, i.url, i.triage_summary, i.triage_score,
                   i.status, i.fetched_at, s.name AS source_name
            FROM items i LEFT JOIN sources s ON s.id = i.source_id
            {where} ORDER BY i.fetched_at DESC LIMIT ?""",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def ops_overview(conn: sqlite3.Connection) -> dict:
    sources = conn.execute(
        "SELECT id, type, name, active, last_fetched_at, fetch_error_count "
        "FROM sources ORDER BY type, name"
    ).fetchall()
    counts = conn.execute(
        "SELECT status, COUNT(*) AS n FROM items GROUP BY status"
    ).fetchall()
    undelivered = conn.execute(
        "SELECT COUNT(*) AS n FROM reports WHERE delivered_at IS NULL"
    ).fetchone()["n"]
    return {
        "sources": [dict(r) for r in sources],
        "inbox_sources": [dict(r) for r in sources if r["type"] == "inbox" and r["active"]],
        "status_counts": {r["status"]: r["n"] for r in counts},
        "undelivered": undelivered,
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_web_queries.py -k "items_feed or ops" -v`
Expected: PASS.

- [ ] **Step 5: Write failing route tests**

Append to `tests/test_web_routes.py`:
```python
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
```

- [ ] **Step 6: Run to verify failure**

Run: `pytest tests/test_web_routes.py -k "items or ops" -v`
Expected: FAIL — routes missing.

- [ ] **Step 7: Add routes and templates**

In `app.py`, add `request` to the flask import:
```python
from flask import Flask, abort, g, render_template, request
```
Add routes inside `create_app`:
```python
    @app.route("/items")
    def items():
        status = request.args.get("status") or None
        source_id = request.args.get("source_id", type=int)
        rows = queries.items_feed(get_conn(), status=status, source_id=source_id)
        ov = queries.ops_overview(get_conn())
        return render_template(
            "items.html", items=rows, inbox_sources=ov["inbox_sources"],
            topics=queries.topic_list(get_conn()), status=status,
        )

    @app.route("/ops")
    def ops():
        from perpetual_analyst.web import actions
        return render_template(
            "ops.html", ov=queries.ops_overview(get_conn()), run_status=actions.run_status(),
        )
```

Add nav links in `base.html` after Topics:
```html
    <a href="{{ url_for('items') }}">Items</a>
    <a href="{{ url_for('ops') }}">Ops</a>
```

Create `src/perpetual_analyst/web/templates/items.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>Items</h1>
<form method="get" class="inline">
  <select name="status" onchange="this.form.submit()">
    <option value="">all statuses</option>
    {% for s in ['new', 'analyzed', 'skipped'] %}
    <option value="{{ s }}" {% if status == s %}selected{% endif %}>{{ s }}</option>
    {% endfor %}
  </select>
</form>
{% if items %}
<table>
  <tr><th>Title</th><th>Source</th><th>Score</th><th>Status</th></tr>
  {% for i in items %}
  <tr>
    <td>{% if i.url %}<a href="{{ i.url }}">{{ i.title or '(untitled)' }}</a>{% else %}{{ i.title or '(untitled)' }}{% endif %}</td>
    <td>{{ i.source_name or '—' }}</td>
    <td>{{ '%.2f'|format(i.triage_score) if i.triage_score is not none else '—' }}</td>
    <td>{{ i.status }}</td>
  </tr>
  {% endfor %}
</table>
{% else %}
<p class="empty">No items{% if status %} with status {{ status }}{% endif %}.</p>
{% endif %}
{% endblock %}
```

Create `src/perpetual_analyst/web/templates/ops.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>Ops</h1>
<section class="card">
  <div class="label">Item status</div>
  {% for k, v in ov.status_counts.items() %}<span>{{ k }}: {{ v }} &nbsp;</span>{% endfor %}
  <div>Undelivered reports: {{ ov.undelivered }}</div>
</section>
<section class="card">
  <div class="label">Sources</div>
  <table>
    <tr><th>Name</th><th>Type</th><th>Active</th><th>Last fetched</th><th>Errors</th></tr>
    {% for s in ov.sources %}
    <tr>
      <td>{{ s.name }}</td><td>{{ s.type }}</td>
      <td>{{ 'yes' if s.active else 'no' }}</td>
      <td>{{ s.last_fetched_at or '—' }}</td>
      <td>{{ s.fetch_error_count }}</td>
    </tr>
    {% endfor %}
  </table>
</section>
{% endblock %}
```

- [ ] **Step 8: Run to verify pass**

Run: `pytest tests/test_web_routes.py tests/test_web_queries.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/perpetual_analyst/web/queries.py src/perpetual_analyst/web/app.py src/perpetual_analyst/web/templates/items.html src/perpetual_analyst/web/templates/ops.html src/perpetual_analyst/web/templates/base.html tests/test_web_queries.py tests/test_web_routes.py
git commit -m "feat(web): items feed and ops overview pages"
```

---

## Task 5: Global Reading mode

**Files:**
- Modify: `src/perpetual_analyst/web/queries.py`
- Modify: `src/perpetual_analyst/web/app.py`
- Create: `src/perpetual_analyst/web/templates/reading.html`
- Modify: `src/perpetual_analyst/web/templates/base.html`
- Modify: `tests/test_web_queries.py`, `tests/test_web_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_web_queries.py`:
```python
def test_all_dossiers(seeded_conn):
    rows = queries.all_dossiers(seeded_conn)
    assert len(rows) == 1
    assert rows[0]["slug"] == "ai-labs"
    assert rows[0]["content"].startswith("## State of play")
```

Append to `tests/test_web_routes.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_web_routes.py -k reading -v`
Expected: FAIL — `/reading` missing; home does not redirect.

- [ ] **Step 3: Add query function**

Append to `src/perpetual_analyst/web/queries.py`:
```python
def all_dossiers(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT t.slug, t.name, d.content, d.updated_at
           FROM topics t JOIN dossiers d ON d.topic_id = t.id
           WHERE t.active = 1 ORDER BY t.name"""
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Add routes, reading-mode redirect, nav toggle**

In `app.py` add `redirect`, `url_for`, `make_response` to imports:
```python
from flask import (Flask, abort, g, make_response, redirect, render_template,
                   request, url_for)
```
Change the `today` route to honor the cookie (add the guard as the first lines):
```python
    @app.route("/")
    def today():
        if request.cookies.get("reading") == "1":
            return redirect(url_for("reading"))
        report = queries.latest_report(get_conn())
        report_html = render_report_html(report["full_markdown"]) if report else ""
        return render_template("today.html", report=report, report_html=report_html)
```
Add the reading routes:
```python
    @app.route("/reading")
    def reading():
        return render_template("reading.html", dossiers=queries.all_dossiers(get_conn()))

    @app.route("/reading/toggle", methods=["POST"])
    def reading_toggle():
        on = request.cookies.get("reading") == "1"
        resp = make_response(redirect(url_for("today")))
        if on:
            resp.delete_cookie("reading")
        else:
            resp.set_cookie("reading", "1")
        return resp
```

In `base.html`, add a reading toggle to the nav (after the Ops link), with a spacer:
```html
    <span class="spacer"></span>
    <form method="post" action="{{ url_for('reading_toggle') }}" class="inline">
      <button class="btn" type="submit">
        {% if request.cookies.get('reading') == '1' %}Exit reading{% else %}Reading mode{% endif %}
      </button>
    </form>
```

Create `src/perpetual_analyst/web/templates/reading.html`:
```html
{% extends "base.html" %}
{% block content %}
<div class="reading">
<h1>Reading</h1>
{% for d in dossiers %}
<article class="card">
  <div class="label"><a href="{{ url_for('topic', slug=d.slug) }}">{{ d.name }}</a> · updated {{ d.updated_at or '—' }}</div>
  <pre style="white-space:pre-wrap">{{ d.content }}</pre>
</article>
{% else %}
<p class="empty">No dossiers yet.</p>
{% endfor %}
</div>
{% endblock %}
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/test_web_routes.py tests/test_web_queries.py -v`
Expected: PASS.

> Note: if `client.set_cookie("reading", "1")` raises a signature error on the
> installed Werkzeug, use `client.set_cookie("localhost", "reading", "1")`.

- [ ] **Step 6: Commit**

```bash
git add src/perpetual_analyst/web/queries.py src/perpetual_analyst/web/app.py src/perpetual_analyst/web/templates/reading.html src/perpetual_analyst/web/templates/base.html tests/test_web_queries.py tests/test_web_routes.py
git commit -m "feat(web): global reading mode (stacked dossiers)"
```

---

## Task 6: Add-inbox action

**Files:**
- Create: `src/perpetual_analyst/web/actions.py`
- Modify: `src/perpetual_analyst/web/app.py`
- Modify: `src/perpetual_analyst/web/templates/items.html`
- Create: `tests/test_web_actions.py`

- [ ] **Step 1: Write failing action tests**

Create `tests/test_web_actions.py`:
```python
import sqlite3

from perpetual_analyst.web import actions


def _conn(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_add_inbox_item_inserts(db_path):
    conn = _conn(db_path)
    ok = actions.add_inbox_item(conn, topic_id=1, title="Note", url=None, text="fresh thought")
    assert ok is True
    row = conn.execute(
        "SELECT * FROM items WHERE raw_text = 'fresh thought'"
    ).fetchone()
    assert row["source_id"] == 2  # the inbox source
    assert row["status"] == "new"
    conn.close()


def test_add_inbox_item_dedupes_silently(db_path):
    conn = _conn(db_path)
    assert actions.add_inbox_item(conn, 1, "Note", None, "same text") is True
    assert actions.add_inbox_item(conn, 1, "Note", None, "same text") is False
    conn.close()


def test_add_inbox_item_no_inbox_source_raises(db_path):
    conn = _conn(db_path)
    conn.execute("DELETE FROM sources WHERE type = 'inbox'")
    conn.commit()
    try:
        actions.add_inbox_item(conn, 1, "Note", None, "text")
        raised = False
    except actions.NoInboxSource:
        raised = True
    assert raised
    conn.close()
```

Append the route test to `tests/test_web_routes.py`:
```python
def test_inbox_post_redirects_and_inserts(client):
    resp = client.post("/actions/inbox", data={"topic_id": "1", "text": "via the web"})
    assert resp.status_code == 302
    follow = client.get("/items")
    assert b"via the web" in follow.data
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_web_actions.py -v`
Expected: FAIL — `perpetual_analyst.web.actions` missing.

- [ ] **Step 3: Create `actions.py` with add_inbox_item**

Create `src/perpetual_analyst/web/actions.py`:
```python
"""Write actions for the dashboard. Each reuses an existing guarded code path."""

from __future__ import annotations

import hashlib
import sqlite3

from perpetual_analyst.store.db import insert_item


class NoInboxSource(Exception):
    """No active inbox source linked to the topic."""


def add_inbox_item(
    conn: sqlite3.Connection,
    topic_id: int,
    title: str | None,
    url: str | None,
    text: str,
) -> bool:
    """Insert pasted text as a new inbox item (next run triages it). Silent dedupe."""
    text = (text or "").strip()
    if not text:
        raise ValueError("empty text")
    row = conn.execute(
        """SELECT s.id FROM sources s
           JOIN topic_sources ts ON ts.source_id = s.id
           WHERE ts.topic_id = ? AND s.type = 'inbox' AND s.active = 1
           LIMIT 1""",
        (topic_id,),
    ).fetchone()
    if row is None:
        raise NoInboxSource(f"no inbox source for topic {topic_id}")
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    inserted = insert_item(
        conn,
        source_id=row["id"],
        content_hash=content_hash,
        title=(title or text[:60]).strip(),
        url=url or None,
        raw_text=text,
    )
    conn.commit()
    return inserted
```

- [ ] **Step 4: Run action unit tests to verify pass**

Run: `pytest tests/test_web_actions.py -v`
Expected: PASS.

- [ ] **Step 5: Add the route and form**

In `app.py`, add `flash` to imports:
```python
from flask import (Flask, abort, flash, g, make_response, redirect,
                   render_template, request, url_for)
```
Add route inside `create_app`:
```python
    @app.route("/actions/inbox", methods=["POST"])
    def action_inbox():
        from perpetual_analyst.web import actions
        topic_id = request.form.get("topic_id", type=int)
        text = request.form.get("text", "")
        title = request.form.get("title") or None
        url = request.form.get("url") or None
        try:
            ok = actions.add_inbox_item(get_conn(), topic_id, title, url, text)
            flash("Item added." if ok else "Duplicate — already present.", "info")
        except actions.NoInboxSource:
            flash("No inbox source for that topic.", "error")
        except ValueError as exc:
            flash(f"Could not add item: {type(exc).__name__}", "error")
        return redirect(url_for("items"))
```

Add the form to the top of `items.html` (after `<h1>Items</h1>`):
```html
{% if inbox_sources %}
<form method="post" action="{{ url_for('action_inbox') }}" class="card">
  <div class="label">Add inbox item</div>
  <select name="topic_id">
    {% for t in topics %}<option value="{{ t.id }}">{{ t.name }}</option>{% endfor %}
  </select>
  <input name="title" placeholder="title (optional)">
  <input name="url" placeholder="url (optional)">
  <input name="text" placeholder="paste text" required>
  <button class="btn" type="submit">Add</button>
</form>
{% endif %}
```

- [ ] **Step 6: Run to verify pass**

Run: `pytest tests/test_web_actions.py tests/test_web_routes.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/perpetual_analyst/web/actions.py src/perpetual_analyst/web/app.py src/perpetual_analyst/web/templates/items.html tests/test_web_actions.py tests/test_web_routes.py
git commit -m "feat(web): add-inbox write action"
```

---

## Task 7: Retry-undelivered action

**Files:**
- Modify: `src/perpetual_analyst/web/actions.py`
- Modify: `src/perpetual_analyst/web/app.py`
- Modify: `src/perpetual_analyst/web/templates/reports.html`
- Modify: `tests/test_web_actions.py`, `tests/test_web_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_web_actions.py`:
```python
def test_telegram_configured_reads_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert actions.telegram_configured() is False
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "y")
    assert actions.telegram_configured() is True


def test_retry_all_calls_delivery(db_path, monkeypatch):
    calls = {}
    monkeypatch.setattr(actions, "retry_undelivered", lambda conn: calls.setdefault("n", 3))
    conn = _conn(db_path)
    assert actions.retry_all(conn) == 3
    assert calls["n"] == 3
    conn.close()
```

Append to `tests/test_web_routes.py`:
```python
def test_retry_route_redirects(client, monkeypatch):
    from perpetual_analyst.web import actions
    monkeypatch.setattr(actions, "retry_undelivered", lambda conn: 1)
    resp = client.post("/actions/retry")
    assert resp.status_code == 302
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_web_actions.py -k "telegram or retry" -v`
Expected: FAIL — undefined.

- [ ] **Step 3: Add action helpers**

Append to `src/perpetual_analyst/web/actions.py`:
```python
import os

from perpetual_analyst.delivery.telegram import retry_undelivered


def telegram_configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def retry_all(conn: sqlite3.Connection) -> int:
    return retry_undelivered(conn)
```
(Move the `import os` to the top import block with the others.)

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_web_actions.py -k "telegram or retry" -v`
Expected: PASS.

- [ ] **Step 5: Add route and control**

In `app.py`, add route:
```python
    @app.route("/actions/retry", methods=["POST"])
    def action_retry():
        from perpetual_analyst.web import actions
        if not actions.telegram_configured():
            flash("Telegram not configured — set TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.", "error")
            return redirect(url_for("reports"))
        try:
            n = actions.retry_all(get_conn())
            flash(f"Delivered {n} report(s).", "info")
        except Exception as exc:  # secret hygiene: type only
            flash(f"Retry failed: {type(exc).__name__}", "error")
        return redirect(url_for("reports"))
```

In `reports()` route, pass the flag:
```python
    @app.route("/reports")
    def reports():
        from perpetual_analyst.web import actions
        return render_template(
            "reports.html", reports=queries.report_list(get_conn()),
            telegram_ok=actions.telegram_configured(),
        )
```

Add the control to `reports.html` (after the `<h1>Reports</h1>`):
```html
{% if reports and reports|selectattr('delivered_at', 'none')|list %}
<form method="post" action="{{ url_for('action_retry') }}" class="inline">
  <button class="btn" type="submit" {% if not telegram_ok %}disabled title="Telegram not configured"{% endif %}>
    Retry undelivered
  </button>
</form>
{% endif %}
```

- [ ] **Step 6: Run to verify pass**

Run: `pytest tests/test_web_actions.py tests/test_web_routes.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/perpetual_analyst/web/actions.py src/perpetual_analyst/web/app.py src/perpetual_analyst/web/templates/reports.html tests/test_web_actions.py tests/test_web_routes.py
git commit -m "feat(web): retry-undelivered write action"
```

---

## Task 8: Trigger-run action (lock + background thread + status)

**Files:**
- Modify: `src/perpetual_analyst/web/actions.py`
- Modify: `src/perpetual_analyst/web/app.py`
- Modify: `src/perpetual_analyst/web/templates/ops.html`
- Modify: `tests/test_web_actions.py`, `tests/test_web_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_web_actions.py`:
```python
import threading
import time


def test_trigger_run_lock_rejects_concurrent(db_path, monkeypatch):
    gate = threading.Event()

    def fake_run_daily(conn, client, settings, dry_run=False):
        gate.wait(timeout=5)

    monkeypatch.setattr(actions, "run_daily", fake_run_daily)
    monkeypatch.setattr(actions, "make_client", lambda: None)
    monkeypatch.setattr(actions, "load_settings", lambda: None)

    actions.reset_run_status()
    assert actions.trigger_run(db_path, dry_run=True) is True
    # second attempt while the first holds the lock
    for _ in range(50):
        if actions.run_status()["state"] == "running":
            break
        time.sleep(0.02)
    assert actions.trigger_run(db_path, dry_run=True) is False
    gate.set()
    for _ in range(50):
        if actions.run_status()["state"] == "done":
            break
        time.sleep(0.02)
    assert actions.run_status()["state"] == "done"
```

Append to `tests/test_web_routes.py`:
```python
def test_run_status_endpoint(client):
    resp = client.get("/actions/run/status")
    assert resp.status_code == 200
    assert resp.json["state"] in {"idle", "running", "done", "error"}
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_web_actions.py -k trigger_run -v`
Expected: FAIL — undefined.

- [ ] **Step 3: Add run orchestration**

Append to `src/perpetual_analyst/web/actions.py`:
```python
import threading
from datetime import datetime, timezone

from perpetual_analyst.analyst.agent import make_client
from perpetual_analyst.config import load_settings
from perpetual_analyst.daily_run import force_utf8_stdout, run_daily
from perpetual_analyst.store.db import init_db

_run_lock = threading.Lock()
_run_status: dict = {"state": "idle", "started_at": None, "finished_at": None,
                     "error": None, "dry_run": False}


def run_status() -> dict:
    return dict(_run_status)


def reset_run_status() -> None:
    _run_status.update(state="idle", started_at=None, finished_at=None,
                       error=None, dry_run=False)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run_worker(db_path: str, dry_run: bool) -> None:
    try:
        force_utf8_stdout()
        conn = init_db(db_path)
        try:
            client = None if dry_run else make_client()
            run_daily(conn, client, load_settings(), dry_run=dry_run)
        finally:
            conn.close()
        _run_status.update(state="done", finished_at=_now())
    except Exception as exc:  # secret hygiene: type only
        _run_status.update(state="error", finished_at=_now(), error=type(exc).__name__)
    finally:
        _run_lock.release()


def trigger_run(db_path: str, dry_run: bool) -> bool:
    """Start a daily run in a background thread. Returns False if one is in flight."""
    if not _run_lock.acquire(blocking=False):
        return False
    _run_status.update(state="running", started_at=_now(), finished_at=None,
                       error=None, dry_run=dry_run)
    thread = threading.Thread(target=_run_worker, args=(db_path, dry_run), daemon=True)
    thread.start()
    return True
```
(Consolidate the duplicate `import threading` / `import os` lines into the top
import block; do not leave repeated imports.)

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_web_actions.py -k trigger_run -v`
Expected: PASS.

- [ ] **Step 5: Add routes and Ops control**

In `app.py`, add routes:
```python
    @app.route("/actions/run", methods=["POST"])
    def action_run():
        from perpetual_analyst.web import actions
        dry_run = request.form.get("dry_run") == "1"
        started = actions.trigger_run(app.config["DB_PATH"], dry_run=dry_run)
        flash("Run started." if started else "A run is already in progress.",
              "info" if started else "error")
        return redirect(url_for("ops"))

    @app.route("/actions/run/status")
    def action_run_status():
        from perpetual_analyst.web import actions
        return actions.run_status()
```

Add to `ops.html` (after the status card), a control + poll script:
```html
<section class="card">
  <div class="label">Daily run</div>
  <div id="run-state">state: {{ run_status.state }}{% if run_status.error %} ({{ run_status.error }}){% endif %}</div>
  <form method="post" action="{{ url_for('action_run') }}" class="inline">
    <button class="btn" type="submit">Trigger run</button>
  </form>
  <form method="post" action="{{ url_for('action_run') }}" class="inline">
    <input type="hidden" name="dry_run" value="1">
    <button class="btn" type="submit">Trigger dry-run</button>
  </form>
</section>
<script>
  async function poll() {
    try {
      const r = await fetch("{{ url_for('action_run_status') }}");
      const s = await r.json();
      document.getElementById("run-state").textContent =
        "state: " + s.state + (s.error ? " (" + s.error + ")" : "");
      if (s.state === "running") setTimeout(poll, 2000);
    } catch (e) {}
  }
  if ("{{ run_status.state }}" === "running") poll();
</script>
```

- [ ] **Step 6: Run to verify pass**

Run: `pytest tests/test_web_actions.py tests/test_web_routes.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/perpetual_analyst/web/actions.py src/perpetual_analyst/web/app.py src/perpetual_analyst/web/templates/ops.html tests/test_web_actions.py tests/test_web_routes.py
git commit -m "feat(web): trigger-run action with single-run lock and status poll"
```

---

## Task 9: `analyst web` CLI command

**Files:**
- Modify: `src/perpetual_analyst/cli.py`
- Modify: `tests/test_web_routes.py` (smoke import test)

- [ ] **Step 1: Write a failing test**

Append to `tests/test_web_routes.py`:
```python
def test_cli_web_command_registered():
    from typer.testing import CliRunner

    from perpetual_analyst.cli import app

    result = CliRunner().invoke(app, ["web", "--help"])
    assert result.exit_code == 0
    assert "host" in result.output.lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_web_routes.py::test_cli_web_command_registered -v`
Expected: FAIL — no `web` command.

- [ ] **Step 3: Add the command**

In `src/perpetual_analyst/cli.py`, add after the `run` command:
```python
@app.command()
def web(
    host: str = typer.Option("127.0.0.1", help="Bind host (loopback by default)"),
    port: int = typer.Option(8080, help="Port"),
    db_path: str = typer.Option("data/analyst.db", help="SQLite DB path"),
) -> None:
    """Launch the local dashboard."""
    from perpetual_analyst.web.app import create_app

    create_app(db_path).run(host=host, port=port)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_web_routes.py::test_cli_web_command_registered -v`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

Run: `pytest -q` (excluding live smoke) — expect all green.
```bash
git add src/perpetual_analyst/cli.py tests/test_web_routes.py
git commit -m "feat(web): analyst web CLI command"
```

---

## Task 10: Full-suite gate + lint

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite**

Run: `pytest -q -m "not smoke"`
Expected: all pass (existing + new web tests).

- [ ] **Step 2: Run pre-commit**

Run: `pre-commit run --all-files`
Expected: ruff + ruff-format pass on the new files. Fix any lint on `web/` and `tests/test_web_*` only; note pre-existing failures on untouched files and proceed.

- [ ] **Step 3: Commit any lint fixes**

```bash
git add -u src/perpetual_analyst/web tests/test_web_queries.py tests/test_web_routes.py tests/test_web_actions.py
git commit -m "style(web): lint fixes"
```

---

## Self-Review

**Spec coverage:**
- 8 read routes → Tasks 1–4 (Today, Topics, Topic, Thesis, Reports, Report detail, Items, Ops). ✓
- Global Reading mode → Task 5. ✓
- 3 write actions (inbox, retry, run) → Tasks 6, 7, 8. ✓
- `analyst web` CLI, loopback default → Task 9. ✓
- Invariant 7 (secrets): retry/run handlers flash `type(exc).__name__` only; no secret rendered. ✓
- Invariant 3 (theses): no thesis writes anywhere. ✓
- Invariant 8 (dedupe): add_inbox returns False on duplicate, never raises. ✓
- Empty states: tested on every read page (Tasks 1–4). ✓
- Bounded live validation: performed in Pre-PR, not a code task (per workflow). ✓

**Placeholder scan:** no TBD/TODO; every step has real code/commands. ✓

**Type consistency:** view-model builders return `dict`/`list[dict]`; routes pass them straight to templates; `actions.add_inbox_item`, `retry_all`, `telegram_configured`, `trigger_run`, `run_status`, `reset_run_status`, `NoInboxSource` names are used identically in tests, actions, and routes. ✓

**Deviation:** add-inbox is text-required (URL optional metadata), logged at the top of this plan and to be recorded in TODO.md.
