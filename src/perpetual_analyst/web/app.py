"""Flask app factory for the local single-user dashboard. Binds loopback only."""

from __future__ import annotations

import sqlite3

import markdown as md
from flask import Flask, abort, g, make_response, redirect, render_template, request, url_for

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
        if request.cookies.get("reading") == "1":
            return redirect(url_for("reading"))
        report = queries.latest_report(get_conn())
        report_html = render_report_html(report["full_markdown"]) if report else ""
        return render_template("today.html", report=report, report_html=report_html)

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

    @app.route("/items")
    def items():
        status = request.args.get("status") or None
        source_id = request.args.get("source_id", type=int)
        rows = queries.items_feed(get_conn(), status=status, source_id=source_id)
        ov = queries.ops_overview(get_conn())
        return render_template(
            "items.html",
            items=rows,
            inbox_sources=ov["inbox_sources"],
            topics=queries.topic_list(get_conn()),
            status=status,
        )

    @app.route("/ops")
    def ops():
        return render_template("ops.html", ov=queries.ops_overview(get_conn()))

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

    return app
