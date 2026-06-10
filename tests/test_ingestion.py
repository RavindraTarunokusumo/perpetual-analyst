from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from perpetual_analyst.ingestion.inbox import scan_inbox
from perpetual_analyst.store.models import Item


@pytest.fixture
def inbox_dir(tmp_path: Path, sample_topic) -> Path:
    topic_dir = tmp_path / "inbox" / sample_topic.slug
    topic_dir.mkdir(parents=True)
    return topic_dir


def _write_file(dir_: Path, name: str, content: str) -> Path:
    p = dir_ / name
    p.write_text(content, encoding="utf-8")
    return p


def test_scan_inbox_ingests_txt_file(
    db: sqlite3.Connection, sample_topic, sample_source: int, inbox_dir: Path, monkeypatch
) -> None:
    monkeypatch.chdir(inbox_dir.parent.parent)
    _write_file(inbox_dir, "article.txt", "This is test article content about AI safety.")

    items = scan_inbox(sample_topic.slug, sample_topic.id, sample_source, db)
    assert len(items) == 1
    assert items[0].title == "article"
    assert "AI safety" in items[0].raw_text


def test_scan_inbox_ingests_md_file(
    db: sqlite3.Connection, sample_topic, sample_source: int, inbox_dir: Path, monkeypatch
) -> None:
    monkeypatch.chdir(inbox_dir.parent.parent)
    _write_file(inbox_dir, "notes.md", "## Key insight\n\nMachines are getting smarter.")

    items = scan_inbox(sample_topic.slug, sample_topic.id, sample_source, db)
    assert len(items) == 1
    assert "Machines are getting smarter" in items[0].raw_text


def test_scan_inbox_deduplicates(
    db: sqlite3.Connection, sample_topic, sample_source: int, inbox_dir: Path, monkeypatch
) -> None:
    monkeypatch.chdir(inbox_dir.parent.parent)
    _write_file(inbox_dir, "first.txt", "Identical content here.")

    items1 = scan_inbox(sample_topic.slug, sample_topic.id, sample_source, db)
    assert len(items1) == 1

    _write_file(inbox_dir, "second.txt", "Identical content here.")

    items2 = scan_inbox(sample_topic.slug, sample_topic.id, sample_source, db)
    assert len(items2) == 0

    count = db.execute("SELECT COUNT(*) FROM items WHERE source_id = ?", (sample_source,)).fetchone()[0]
    assert count == 1


def test_scan_inbox_moves_to_processed(
    db: sqlite3.Connection, sample_topic, sample_source: int, inbox_dir: Path, monkeypatch
) -> None:
    monkeypatch.chdir(inbox_dir.parent.parent)
    src = _write_file(inbox_dir, "doc.txt", "Move me to processed dir.")

    scan_inbox(sample_topic.slug, sample_topic.id, sample_source, db)

    assert not src.exists()
    assert (inbox_dir / ".processed" / "doc.txt").exists()


def test_scan_inbox_skips_hidden_files(
    db: sqlite3.Connection, sample_topic, sample_source: int, inbox_dir: Path, monkeypatch
) -> None:
    monkeypatch.chdir(inbox_dir.parent.parent)
    _write_file(inbox_dir, ".hidden", "Should be ignored.")
    _write_file(inbox_dir, "visible.txt", "Should be ingested.")

    items = scan_inbox(sample_topic.slug, sample_topic.id, sample_source, db)
    assert len(items) == 1
    assert items[0].title == "visible"


def test_scan_inbox_skips_unsupported_extensions(
    db: sqlite3.Connection, sample_topic, sample_source: int, inbox_dir: Path, monkeypatch
) -> None:
    monkeypatch.chdir(inbox_dir.parent.parent)
    _write_file(inbox_dir, "data.csv", "col1,col2\n1,2")
    _write_file(inbox_dir, "doc.txt", "Valid document.")

    items = scan_inbox(sample_topic.slug, sample_topic.id, sample_source, db)
    assert len(items) == 1


def test_scan_inbox_returns_empty_for_missing_dir(
    db: sqlite3.Connection, sample_topic, sample_source: int, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    items = scan_inbox("nonexistent-topic", sample_topic.id, sample_source, db)
    assert items == []
