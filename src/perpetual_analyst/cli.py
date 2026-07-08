"""typer CLI app. Installed as `analyst` script via pyproject.toml. See SPEC §3."""

from __future__ import annotations

import os
import re
import sqlite3

import typer
from dotenv import load_dotenv

from perpetual_analyst.store.db import init_db

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")

load_dotenv()

app = typer.Typer(help="Perpetual Analyst CLI")

topic_app = typer.Typer(help="Manage topics")
source_app = typer.Typer(help="Manage sources")
report_app = typer.Typer(help="View reports")

app.add_typer(topic_app, name="topic")
app.add_typer(source_app, name="source")
app.add_typer(report_app, name="report")


def _db() -> sqlite3.Connection:
    path = os.environ.get("ANALYST_DB_PATH", "data/analyst.db")
    return init_db(path)


@topic_app.command("add")
def topic_add(
    slug: str = typer.Argument(help="URL-safe topic slug (lowercase, a-z0-9_-)"),
    name: str = typer.Option(..., help="Display name"),
    brief: str = typer.Option(None, help="One-paragraph analyst brief"),
) -> None:
    """Register a new topic and create its inbox source."""
    if not _SLUG_RE.match(slug):
        typer.echo(f"Invalid slug '{slug}' — must match [a-z0-9][a-z0-9_-]{{0,62}}", err=True)
        raise typer.Exit(1)
    conn = _db()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO topics (slug, name, brief, user_id) VALUES (?, ?, ?, 1)",
                (slug, name, brief),
            )
            topic_id = cur.lastrowid
            src_cur = conn.execute(
                "INSERT INTO sources (type, name, active) VALUES ('inbox', ?, 1)",
                (f"inbox:{slug}",),
            )
            conn.execute(
                "INSERT INTO topic_sources (topic_id, source_id) VALUES (?, ?)",
                (topic_id, src_cur.lastrowid),
            )
        typer.echo(f"Added topic '{slug}'.")
    except sqlite3.IntegrityError as exc:
        msg = (
            f"Topic '{slug}' already exists."
            if "UNIQUE" in str(exc).upper()
            else f"DB error: {exc}"
        )
        typer.echo(msg, err=True)
        raise typer.Exit(1)


@topic_app.command("list")
def topic_list() -> None:
    """List all topics."""
    conn = _db()
    rows = conn.execute(
        "SELECT slug, name, brief, active FROM topics ORDER BY created_at"
    ).fetchall()
    if not rows:
        typer.echo("No topics.")
        return
    for row in rows:
        status = "active" if row["active"] else "inactive"
        brief_preview = f"  {row['brief'][:80]}" if row["brief"] else ""
        typer.echo(f"{row['slug']:30} {row['name']:30} [{status}]{brief_preview}")


@source_app.command("add")
def source_add(
    topic: str = typer.Option(..., help="Topic slug"),
    type_: str = typer.Option(..., "--type", help="Source type (rss, inbox, web)"),
    url: str = typer.Option(None, help="Source URL"),
    name: str = typer.Option(None, help="Source display name"),
) -> None:
    """Add a source and link it to a topic."""
    conn = _db()
    topic_row = conn.execute("SELECT id FROM topics WHERE slug = ?", (topic,)).fetchone()
    if not topic_row:
        typer.echo(f"Topic '{topic}' not found.", err=True)
        raise typer.Exit(1)
    cur = conn.execute(
        "INSERT INTO sources (type, url, name, active, status, probation_until)"
        " VALUES (?, ?, ?, 1, 'probation', datetime('now', '+21 days'))",
        (type_, url, name),
    )
    source_id = cur.lastrowid
    conn.execute(
        "INSERT INTO topic_sources (topic_id, source_id) VALUES (?, ?)",
        (topic_row["id"], source_id),
    )
    conn.commit()
    typer.echo(f"Added source id={source_id} ({type_}) to topic '{topic}' (probation, 21 days).")


@source_app.command("list")
def source_list(
    topic: str = typer.Option(..., help="Topic slug"),
) -> None:
    """List sources for a topic."""
    conn = _db()
    rows = conn.execute(
        """SELECT s.id, s.type, s.url, s.name, s.active
           FROM sources s
           JOIN topic_sources ts ON ts.source_id = s.id
           JOIN topics t ON t.id = ts.topic_id
           WHERE t.slug = ?
           ORDER BY s.id""",
        (topic,),
    ).fetchall()
    if not rows:
        typer.echo("No sources.")
        return
    for row in rows:
        status = "active" if row["active"] else "inactive"
        name = row["name"] or ""
        url = row["url"] or ""
        typer.echo(f"[{row['id']:3}] {row['type']:10} [{status}]  {name:20} {url}")


@source_app.command("candidates")
def source_candidates(
    topic: str = typer.Option(None, help="Topic slug to filter (default: all)"),
) -> None:
    """List discovered source candidates awaiting review (read-only)."""
    conn = _db()
    topic_id: int | None = None
    if topic is not None:
        row = conn.execute("SELECT id FROM topics WHERE slug = ?", (topic,)).fetchone()
        if not row:
            typer.echo(f"Topic '{topic}' not found.", err=True)
            raise typer.Exit(1)
        topic_id = row["id"]

    query = "SELECT sc.id, sc.status, sc.domain, sc.url, sc.rationale FROM source_candidates sc"
    params: tuple = ()
    if topic_id is not None:
        query += " WHERE sc.topic_id = ?"
        params = (topic_id,)
    query += " ORDER BY sc.created_at"
    rows = conn.execute(query, params).fetchall()

    if not rows:
        typer.echo("No candidates.")
        return

    for row in rows:
        label = row["domain"] or row["url"] or ""
        rationale = (row["rationale"] or "")[:80]
        typer.echo(f"[{row['id']}] {row['status']:8} {label}  — {rationale}")


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", help="Host interface for the local operator UI"),
    port: int = typer.Option(8765, help="Port for the local operator UI"),
) -> None:
    """Serve the local source approval and quality dashboard."""
    from perpetual_analyst.web import serve_dashboard

    serve_dashboard(host=host, port=port)


@app.command()
def weekly(
    topic: str = typer.Option(None, help="Topic slug to compact (default: all active)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print prompt, skip API calls"),
) -> None:
    """Run the weekly memory-compaction pass."""
    from perpetual_analyst.weekly_run import main as weekly_main

    weekly_main(dry_run=dry_run, topic_slug=topic)


@app.command()
def run(
    topic: str = typer.Option(None, help="Topic slug to run (default: all active)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print prompt, skip API calls"),
) -> None:
    """Run the daily analyst pipeline (ingest -> triage -> narrative update -> report)."""
    from perpetual_analyst.daily_run import main as daily_main

    daily_main(dry_run=dry_run, topic_slug=topic)


@report_app.command("show")
def report_show(
    date: str = typer.Option(None, help="Report date YYYY-MM-DD (default: latest)"),
) -> None:
    """Show a stored report."""
    conn = _db()
    if date:
        row = conn.execute(
            "SELECT report_date, full_markdown FROM reports WHERE report_date = ?",
            (date,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT report_date, full_markdown FROM reports ORDER BY report_date DESC LIMIT 1"
        ).fetchone()
    if not row:
        typer.echo("No report found.", err=True)
        raise typer.Exit(1)
    typer.echo(f"=== Report: {row['report_date']} ===\n")
    typer.echo(row["full_markdown"] or "(empty report)")


if __name__ == "__main__":
    app()
