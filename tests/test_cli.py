from __future__ import annotations

import sqlite3

import yaml
from typer.testing import CliRunner

from perpetual_analyst import cli

runner = CliRunner()


def _write_configs(tmp_path, monkeypatch):
    topics_path = tmp_path / "topics.yaml"
    sources_path = tmp_path / "sources.yaml"
    topics_path.write_text("topics: []\n", encoding="utf-8")
    sources_path.write_text("sources: []\n", encoding="utf-8")
    monkeypatch.setattr(cli, "TOPICS_PATH", str(topics_path))
    monkeypatch.setattr(cli, "SOURCES_PATH", str(sources_path))
    return topics_path, sources_path


def _query_one(db_path, sql):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(sql).fetchone()
    conn.close()
    return row


def test_topic_add_appends_yaml_and_syncs(tmp_path, monkeypatch):
    topics_path, _ = _write_configs(tmp_path, monkeypatch)
    db_path = str(tmp_path / "test.db")
    result = runner.invoke(
        cli.app,
        [
            "topic",
            "add",
            "ai-labs",
            "--name",
            "AI Labs",
            "--brief",
            "Track the labs",
            "--db-path",
            db_path,
        ],
    )
    assert result.exit_code == 0, result.output
    data = yaml.safe_load(topics_path.read_text(encoding="utf-8"))
    assert data["topics"][0]["slug"] == "ai-labs"
    row = _query_one(db_path, "SELECT * FROM topics WHERE slug = 'ai-labs'")
    assert row["name"] == "AI Labs"


def test_topic_add_duplicate_slug_fails(tmp_path, monkeypatch):
    _write_configs(tmp_path, monkeypatch)
    db_path = str(tmp_path / "test.db")
    args = ["topic", "add", "ai-labs", "--name", "AI Labs", "--db-path", db_path]
    assert runner.invoke(cli.app, args).exit_code == 0
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_source_add_appends_yaml_and_links_topic(tmp_path, monkeypatch):
    _, sources_path = _write_configs(tmp_path, monkeypatch)
    db_path = str(tmp_path / "test.db")
    runner.invoke(cli.app, ["topic", "add", "ai-labs", "--name", "AI Labs", "--db-path", db_path])
    result = runner.invoke(
        cli.app,
        [
            "source",
            "add",
            "--topic",
            "ai-labs",
            "--type",
            "rss",
            "--url",
            "https://a.example/feed",
            "--name",
            "Feed A",
            "--db-path",
            db_path,
        ],
    )
    assert result.exit_code == 0, result.output
    data = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    assert data["sources"][0]["url"] == "https://a.example/feed"
    row = _query_one(
        db_path,
        "SELECT COUNT(*) AS n FROM topic_sources ts"
        " JOIN topics t ON t.id = ts.topic_id WHERE t.slug = 'ai-labs'",
    )
    assert row["n"] == 1


def test_source_add_unknown_topic_fails(tmp_path, monkeypatch):
    _write_configs(tmp_path, monkeypatch)
    db_path = str(tmp_path / "test.db")
    result = runner.invoke(
        cli.app,
        [
            "source",
            "add",
            "--topic",
            "nope",
            "--type",
            "rss",
            "--url",
            "https://a.example/feed",
            "--name",
            "Feed A",
            "--db-path",
            db_path,
        ],
    )
    assert result.exit_code == 1
