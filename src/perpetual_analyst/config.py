from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ModelConfig:
    id: str
    thinking: bool = False


@dataclass
class Settings:
    analyst: ModelConfig
    triage: ModelConfig


def load_settings(path: str = "config/settings.yaml") -> Settings:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    models = data["models"]
    return Settings(
        analyst=ModelConfig(**models["analyst"]),
        triage=ModelConfig(**models["triage"]),
    )


@dataclass
class TopicConfig:
    slug: str
    name: str
    brief: str | None = None
    active: bool = True


@dataclass
class SourceConfig:
    name: str
    type: str
    url: str | None = None
    active: bool = True
    topics: list[str] = field(default_factory=list)


def load_topics(path: str = "config/topics.yaml") -> list[TopicConfig]:
    p = Path(path)
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return [TopicConfig(**entry) for entry in data.get("topics") or []]


def load_sources(path: str = "config/sources.yaml") -> list[SourceConfig]:
    p = Path(path)
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return [SourceConfig(**entry) for entry in data.get("sources") or []]


def sync_config(
    conn: sqlite3.Connection,
    topics: list[TopicConfig],
    sources: list[SourceConfig],
) -> None:
    """Upsert YAML-defined topics/sources into the DB. Idempotent.

    Touches definition columns only — never last_fetched_at, fetch_error_count,
    or quality_score. Rows absent from YAML are deactivated, never deleted;
    inbox-type sources are exempt (they're created implicitly).

    An empty topics/sources list deactivates ALL rows of that kind (inbox
    sources exempt) — an accidentally empty YAML file disables everything.
    """
    for tc in topics:
        conn.execute(
            """INSERT INTO topics (slug, name, brief, active) VALUES (?, ?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET
                 name = excluded.name, brief = excluded.brief, active = excluded.active""",
            (tc.slug, tc.name, tc.brief, int(tc.active)),
        )

    slugs = [tc.slug for tc in topics]
    if slugs:
        slug_placeholders = ",".join("?" for _ in slugs)
        conn.execute(
            f"UPDATE topics SET active = 0 WHERE slug NOT IN ({slug_placeholders})",
            slugs,
        )
    else:
        print("[config] topics list empty - deactivating ALL topics")
        conn.execute("UPDATE topics SET active = 0")

    synced_ids: list[int] = []
    for sc in sources:
        key_column = "url" if sc.url else "name"
        assert key_column in ("url", "name")  # bounded; never user-controlled
        key_value = sc.url or sc.name
        row = conn.execute(
            f"SELECT id, active FROM sources WHERE {key_column} = ?", (key_value,)
        ).fetchone()
        if row:
            source_id = row["id"]
            conn.execute(
                "UPDATE sources SET name = ?, type = ?, url = ?, active = ? WHERE id = ?",
                (sc.name, sc.type, sc.url, int(sc.active), source_id),
            )
            if sc.active and row["active"] == 0:
                conn.execute("UPDATE sources SET fetch_error_count = 0 WHERE id = ?", (source_id,))
        else:
            cur = conn.execute(
                "INSERT INTO sources (name, type, url, active) VALUES (?, ?, ?, ?)",
                (sc.name, sc.type, sc.url, int(sc.active)),
            )
            source_id = cur.lastrowid
        synced_ids.append(source_id)

        conn.execute("DELETE FROM topic_sources WHERE source_id = ?", (source_id,))
        for slug in sc.topics:
            topic_row = conn.execute("SELECT id FROM topics WHERE slug = ?", (slug,)).fetchone()
            if topic_row is None:
                raise ValueError(f"source {sc.name!r} references unknown topic {slug!r}")
            conn.execute(
                "INSERT OR IGNORE INTO topic_sources (topic_id, source_id) VALUES (?, ?)",
                (topic_row["id"], source_id),
            )

    if synced_ids:
        id_placeholders = ",".join("?" for _ in synced_ids)
        conn.execute(
            f"UPDATE sources SET active = 0"
            f" WHERE type != 'inbox' AND id NOT IN ({id_placeholders})",
            synced_ids,
        )
    else:
        conn.execute("UPDATE sources SET active = 0 WHERE type != 'inbox'")

    conn.commit()
