"""typer CLI app. Installed as `analyst` script via pyproject.toml. See SPEC §3.

Note: yaml.safe_dump rewrites drop hand-written comments in the config files.
"""

from __future__ import annotations

from pathlib import Path

import typer
import yaml

from perpetual_analyst.config import load_sources, load_topics, sync_config
from perpetual_analyst.store.db import init_db

app = typer.Typer(help="Perpetual Analyst CLI")

topic_app = typer.Typer(help="Manage topics")
source_app = typer.Typer(help="Manage sources")
report_app = typer.Typer(help="Reports")

app.add_typer(topic_app, name="topic")
app.add_typer(source_app, name="source")
app.add_typer(report_app, name="report")

TOPICS_PATH = "config/topics.yaml"
SOURCES_PATH = "config/sources.yaml"


def _sync(db_path: str) -> None:
    conn = init_db(db_path)
    try:
        sync_config(conn, load_topics(TOPICS_PATH), load_sources(SOURCES_PATH))
    finally:
        conn.close()


def _read_yaml(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def _write_yaml(path: str, data: dict) -> None:
    Path(path).write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


@topic_app.command("add")
def topic_add(
    slug: str,
    name: str = typer.Option(..., help="Display name"),
    brief: str = typer.Option(None, help="What you care about — seeds the dossier"),
    db_path: str = typer.Option("data/analyst.db", help="SQLite DB path"),
) -> None:
    """Add a topic to config/topics.yaml and sync to the DB."""
    data = _read_yaml(TOPICS_PATH)
    topics = data.get("topics") or []
    if any(entry["slug"] == slug for entry in topics):
        typer.echo(f"topic {slug!r} already exists")
        raise typer.Exit(1)
    topics.append({"slug": slug, "name": name, "brief": brief, "active": True})
    data["topics"] = topics
    _write_yaml(TOPICS_PATH, data)
    _sync(db_path)
    typer.echo(f"added topic {slug!r}")


@source_app.command("add")
def source_add(
    topic: str = typer.Option(..., help="Topic slug to link"),
    type: str = typer.Option("rss", help="Source type: rss | inbox | web"),
    url: str = typer.Option(None, help="Feed/site URL"),
    name: str = typer.Option(..., help="Source display name"),
    db_path: str = typer.Option("data/analyst.db", help="SQLite DB path"),
) -> None:
    """Add a source to config/sources.yaml, link it to a topic, and sync to the DB."""
    data = _read_yaml(SOURCES_PATH)
    sources = data.get("sources") or []
    for entry in sources:
        if (url and entry.get("url") == url) or (not url and entry.get("name") == name):
            if topic not in (entry.get("topics") or []):
                entry.setdefault("topics", []).append(topic)
            break
    else:
        sources.append({"name": name, "type": type, "url": url, "active": True, "topics": [topic]})
    data["sources"] = sources
    _write_yaml(SOURCES_PATH, data)
    try:
        _sync(db_path)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    typer.echo(f"added source {name!r} → topic {topic!r}")


@app.command()
def run(
    topic: str = typer.Option(None, help="Topic slug to run (default: all active)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print prompt, skip API calls"),
) -> None:
    """Run the daily analyst pipeline."""
    raise NotImplementedError("TODO Task 10 (Phase 3)")


if __name__ == "__main__":
    app()
