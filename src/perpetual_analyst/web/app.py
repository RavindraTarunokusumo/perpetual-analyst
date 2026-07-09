"""Flask app factory for the local single-user dashboard. Binds loopback only."""

from __future__ import annotations

import os
import sqlite3
from urllib.parse import urlparse

import markdown as md
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from perpetual_analyst.web import queries


def render_markdown(text: str | None) -> str:
    if not text:
        return ""
    # Source is analyst-controlled markdown stored locally; rendered with |safe
    # and no HTML sanitization (loopback-only single-user tool). The [item:N]
    # citation path is retired (provenance lives in Postgres claim_evidence),
    # so report markdown renders directly.
    return md.markdown(text, extensions=["fenced_code", "tables", "footnotes"])


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

    @app.before_request
    def _csrf_origin_guard() -> None:
        # CSRF defense for a no-auth loopback tool: reject any cross-origin
        # state-changing request. Browsers always send Origin on such POSTs;
        # same-origin form posts and non-browser clients (no Origin) pass.
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return
        origin = request.headers.get("Origin")
        if origin is not None and urlparse(origin).netloc != request.host:
            abort(403)

    app.jinja_env.filters["markdown"] = render_markdown

    @app.route("/")
    def today():
        if request.cookies.get("reading") == "1":
            return redirect(url_for("reading"))
        report = queries.latest_report(get_conn())
        changes = queries.today_changes(get_conn(), report["report_date"]) if report else []
        report_html = render_markdown(report["full_markdown"]) if report else ""
        return render_template(
            "today.html", report=report, report_html=report_html, changes=changes
        )

    @app.route("/reports")
    def reports():
        from perpetual_analyst.web import actions

        return render_template(
            "reports.html",
            reports=queries.report_list(get_conn()),
            telegram_ok=actions.telegram_configured(),
        )

    @app.route("/actions/retry", methods=["POST"])
    def action_retry():
        from perpetual_analyst.web import actions

        if not actions.telegram_configured():
            flash("Telegram not configured — set TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.", "error")
            return redirect(url_for("reports"))
        try:
            n = actions.retry_all(get_conn())
            flash(f"Delivered {n} report(s).", "info")
        except Exception as exc:  # secret hygiene: type name only, never the message
            flash(f"Retry failed: {type(exc).__name__}", "error")
        return redirect(url_for("reports"))

    @app.route("/reports/<report_date>")
    def report_detail(report_date: str):
        report = queries.report_by_date(get_conn(), report_date)
        if report is None:
            abort(404)
        report_html = render_markdown(report["full_markdown"])
        return render_template("report_detail.html", report=report, report_html=report_html)

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
        conn = get_conn()
        detail = queries.thesis_detail(conn, thesis_id)
        topic_id = queries.topic_id_for_slug(conn, slug)
        if detail is None or topic_id is None or detail["thesis"]["topic_id"] != topic_id:
            abort(404)
        return render_template("thesis.html", slug=slug, **detail)

    @app.route("/items")
    def items():
        status = request.args.get("status") or None
        source_id = request.args.get("source_id", type=int)
        rows = queries.items_feed(get_conn(), status=status, source_id=source_id)
        return render_template(
            "items.html",
            items=rows,
            inbox_sources=queries.inbox_sources(get_conn()),
            topics=queries.topic_list(get_conn()),
            status=status,
        )

    @app.route("/actions/inbox", methods=["POST"])
    def action_inbox():
        from perpetual_analyst.web import actions

        topic_id = request.form.get("topic_id", type=int)
        text = request.form.get("text", "")
        title = request.form.get("title") or None
        url = request.form.get("url") or None
        if topic_id is None:
            flash("Invalid topic.", "error")
            return redirect(url_for("items"))
        try:
            ok = actions.add_inbox_item(get_conn(), topic_id, title, url, text)
            flash("Item added." if ok else "Duplicate — already present.", "info")
        except actions.NoInboxSource:
            flash("No inbox source for that topic.", "error")
        except ValueError as exc:
            flash(f"Could not add item: {type(exc).__name__}", "error")
        return redirect(url_for("items"))

    @app.route("/ops")
    def ops():
        from perpetual_analyst.web import actions

        return render_template(
            "ops.html",
            ov=queries.ops_overview(get_conn()),
            run_status=actions.run_status(),
        )

    @app.route("/actions/run", methods=["POST"])
    def action_run():
        from perpetual_analyst.web import actions

        dry_run = request.form.get("dry_run") == "1"
        started = actions.trigger_run(app.config["DB_PATH"], dry_run=dry_run)
        flash(
            "Run started." if started else "A run is already in progress.",
            "info" if started else "error",
        )
        return redirect(url_for("ops"))

    @app.route("/actions/run/status")
    def action_run_status():
        from perpetual_analyst.web import actions

        return jsonify(actions.run_status())

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
            resp.set_cookie("reading", "1", httponly=True, samesite="Lax")
        return resp

    return app


def serve_dashboard(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the local dashboard against ANALYST_DB_PATH (default data/analyst.db)."""
    db_path = os.environ.get("ANALYST_DB_PATH", "data/analyst.db")
    create_app(db_path).run(host=host, port=port)
