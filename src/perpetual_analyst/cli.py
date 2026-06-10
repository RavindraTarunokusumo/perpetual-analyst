"""typer CLI app. Installed as `analyst` script via pyproject.toml. See SPEC §3."""

from __future__ import annotations

import os
import re
import sqlite3
import sys

import typer
from dotenv import load_dotenv

from perpetual_analyst.ingestion.inbox import get_or_create_inbox_source
from perpetual_analyst.store.db import init_db
from perpetual_analyst.store.models import Topic

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
        "INSERT INTO sources (type, url, name, active) VALUES (?, ?, ?, 1)",
        (type_, url, name),
    )
    source_id = cur.lastrowid
    conn.execute(
        "INSERT INTO topic_sources (topic_id, source_id) VALUES (?, ?)",
        (topic_row["id"], source_id),
    )
    conn.commit()
    typer.echo(f"Added source id={source_id} ({type_}) to topic '{topic}'.")


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


@app.command()
def run(
    topic: str = typer.Option(None, help="Topic slug to run (default: all active)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print prompt, skip API calls"),
) -> None:
    """Run the daily analyst pipeline."""
    from perpetual_analyst.analyst.agent import make_client, run_topic
    from perpetual_analyst.analyst.triage import triage_items
    from perpetual_analyst.config import load_settings
    from perpetual_analyst.ingestion.inbox import scan_inbox
    from perpetual_analyst.ingestion.rss import fetch_rss
    from perpetual_analyst.store.models import Source

    conn = _db()
    settings = load_settings()

    if topic:
        row = conn.execute("SELECT * FROM topics WHERE slug = ?", (topic,)).fetchone()
        if not row:
            typer.echo(f"Topic '{topic}' not found.", err=True)
            raise typer.Exit(1)
        topics = [Topic.from_row(row)]
    else:
        rows = conn.execute("SELECT * FROM topics WHERE active = 1").fetchall()
        topics = [Topic.from_row(r) for r in rows]

    if not topics:
        typer.echo("No active topics.")
        return

    if dry_run and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    client = None if dry_run else make_client()

    for t in topics:
        typer.echo(f"[run] topic={t.slug}")
        source_id = get_or_create_inbox_source(conn, t.id, t.slug)
        items = scan_inbox(t.slug, t.id, source_id, conn)
        typer.echo(f"[run] {len(items)} item(s) from inbox")

        rss_rows = conn.execute(
            """SELECT s.* FROM sources s
               JOIN topic_sources ts ON ts.source_id = s.id
               WHERE ts.topic_id = ? AND s.type = 'rss' AND s.active = 1""",
            (t.id,),
        ).fetchall()
        for rss_row in rss_rows:
            rss_items = fetch_rss(Source.from_row(rss_row), conn)
            items += rss_items
            typer.echo(f"[run] {len(rss_items)} item(s) from rss source {rss_row['id']}")

        if client is not None and items:
            items = triage_items(items, t.brief or "", client, settings, conn)
            typer.echo(f"[run] {len(items)} item(s) after triage")

        result = run_topic(t, items, conn, client, settings, dry_run=dry_run)
        if result is not None:
            typer.echo(f"[run] done — nothing_significant={result.nothing_significant}")


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
