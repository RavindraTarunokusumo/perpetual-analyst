# Phase 1 — Analyst Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the DB layer, memory module, analyst agent call, and inbox ingestion so a single `analyst run --dry-run` assembles a full context from hand-dropped documents.

**Architecture:** Explicit SQLite connection injection throughout; OpenRouter via `openai` SDK for model calls; character heuristic for pre-call token budgeting with `response.usage` for post-call tracking. Tasks 2, 3, and 5 are independent and run in parallel after Task 1 lands. Task 4 waits for Tasks 2 and 3.

**Tech Stack:** Python 3.14, sqlite3 + FTS5, pydantic v2, openai SDK (OpenRouter), pypdf, python-dotenv, pyyaml, pytest

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/perpetual_analyst/config.py` | Create | Load `config/settings.yaml` into `Settings` dataclass |
| `config/settings.yaml` | Create | Model IDs + thinking flags |
| `src/perpetual_analyst/store/db.py` | Implement | `init_db()` — full DDL, FTS5, triggers, pragmas |
| `src/perpetual_analyst/store/models.py` | Implement | `@dataclass` row types for every table |
| `tests/conftest.py` | Implement | `db`, `sample_topic`, `sample_items`, `mock_openrouter` fixtures |
| `tests/test_store.py` | Create | Schema, FTS triggers, dedupe |
| `src/perpetual_analyst/analyst/memory.py` | Implement | Dossier/observation/thesis CRUD + `build_memory_context` + `apply_all_memory_writes` |
| `tests/test_memory.py` | Create | CRUD correctness, budget truncation, transactional writes |
| `src/perpetual_analyst/analyst/prompts/analyst_system.md` | Finalize | Full system prompt with context template and JSON schema guidance |
| `src/perpetual_analyst/analyst/agent.py` | Implement | Context assembly, OpenRouter call, dry-run, memory commit |
| `tests/test_agent.py` | Create | Context assembly order, dry-run, transaction rollback |
| `src/perpetual_analyst/ingestion/inbox.py` | Implement | Scan inbox, extract, hash-dedupe, move to .processed |
| `tests/test_ingestion.py` | Create | PDF+text extraction, dedupe, .processed move |

---

## Task 1 — DB Layer, Row Models, Settings

**Files:**
- Create: `src/perpetual_analyst/config.py`
- Create: `config/settings.yaml`
- Implement: `src/perpetual_analyst/store/db.py`
- Implement: `src/perpetual_analyst/store/models.py`
- Implement: `tests/conftest.py`
- Create: `tests/test_store.py`

### Step 1.1 — Write failing tests for schema + FTS + dedupe

- [ ] Create `tests/test_store.py`:

```python
import sqlite3
import pytest
from perpetual_analyst.store.db import init_db


def test_init_db_creates_all_tables(db: sqlite3.Connection) -> None:
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    tables = {r[0] for r in rows}
    expected = {
        "users", "topics", "sources", "topic_sources",
        "items", "chunks", "dossiers", "theses", "thesis_updates",
        "observations", "reports",
    }
    assert expected.issubset(tables)


def test_init_db_creates_fts_tables(db: sqlite3.Connection) -> None:
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r[0] for r in rows}
    assert "items_fts" in names
    assert "observations_fts" in names


def test_fts_syncs_on_item_insert(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO sources (id, type) VALUES (1, 'inbox')")
    db.execute(
        "INSERT INTO items (source_id, content_hash, title, raw_text) "
        "VALUES (1, 'hash_fts', 'FTS Title', 'hello searchable world')"
    )
    db.commit()
    results = db.execute(
        "SELECT rowid FROM items_fts WHERE items_fts MATCH 'searchable'"
    ).fetchall()
    assert len(results) == 1


def test_fts_syncs_on_item_delete(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO sources (id, type) VALUES (1, 'inbox')")
    db.execute(
        "INSERT INTO items (source_id, content_hash, title, raw_text) "
        "VALUES (1, 'hash_del', 'Del Title', 'delete me content')"
    )
    db.commit()
    db.execute("DELETE FROM items WHERE content_hash = 'hash_del'")
    db.commit()
    results = db.execute(
        "SELECT rowid FROM items_fts WHERE items_fts MATCH 'delete'",
    ).fetchall()
    assert len(results) == 0


def test_content_hash_deduplication(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO sources (id, type) VALUES (1, 'inbox')")
    db.execute(
        "INSERT INTO items (source_id, content_hash, title, raw_text) "
        "VALUES (1, 'duphash', 'First', 'text')"
    )
    db.execute(
        "INSERT OR IGNORE INTO items (source_id, content_hash, title, raw_text) "
        "VALUES (1, 'duphash', 'Second', 'text2')"
    )
    db.commit()
    count = db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    assert count == 1


def test_foreign_keys_enabled(db: sqlite3.Connection) -> None:
    result = db.execute("PRAGMA foreign_keys").fetchone()
    assert result[0] == 1
```

- [ ] Run tests (expect ImportError / failures since `init_db` not implemented):

```
cd C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst
.venv\Scripts\pytest tests/test_store.py -v 2>&1 | head -30
```

Expected: `ImportError` or `ModuleNotFoundError` for `perpetual_analyst.store.db`.

### Step 1.2 — Implement `store/models.py`

- [ ] Replace the stub with:

```python
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class User:
    id: int
    telegram_chat_id: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "User":
        return cls(**dict(row))


@dataclass
class Topic:
    id: int
    user_id: int | None
    slug: str
    name: str
    brief: str | None
    active: int
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Topic":
        return cls(**dict(row))


@dataclass
class Source:
    id: int
    type: str
    url: str | None
    name: str | None
    active: int
    last_fetched_at: str | None
    fetch_error_count: int
    quality_score: float | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Source":
        return cls(**dict(row))


@dataclass
class Item:
    id: int
    source_id: int | None
    url: str | None
    content_hash: str
    title: str | None
    author: str | None
    published_at: str | None
    fetched_at: str
    raw_text: str | None
    triage_summary: str | None
    triage_score: float | None
    status: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Item":
        return cls(**dict(row))


@dataclass
class Dossier:
    topic_id: int
    content: str
    updated_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Dossier":
        return cls(**dict(row))


@dataclass
class Thesis:
    id: int
    topic_id: int
    statement: str
    rationale: str | None
    confidence: float | None
    status: str
    created_at: str
    updated_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Thesis":
        return cls(**dict(row))


@dataclass
class ThesisUpdate:
    id: int
    thesis_id: int
    change: str
    confidence_before: float | None
    confidence_after: float | None
    triggered_by_item_id: int | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ThesisUpdate":
        return cls(**dict(row))


@dataclass
class Observation:
    id: int
    topic_id: int
    kind: str
    content: str
    importance: int
    source_item_ids: str | None  # JSON array string
    status: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Observation":
        return cls(**dict(row))


@dataclass
class Report:
    id: int
    user_id: int | None
    report_date: str
    digest_text: str | None
    full_markdown: str | None
    delivered_at: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Report":
        return cls(**dict(row))
```

### Step 1.3 — Implement `store/db.py`

- [ ] Replace the stub with:

```python
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    telegram_chat_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    brief TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    url TEXT,
    name TEXT,
    active INTEGER DEFAULT 1,
    last_fetched_at TEXT,
    fetch_error_count INTEGER DEFAULT 0,
    quality_score REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS topic_sources (
    topic_id INTEGER REFERENCES topics(id),
    source_id INTEGER REFERENCES sources(id),
    PRIMARY KEY (topic_id, source_id)
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id),
    url TEXT,
    content_hash TEXT UNIQUE,
    title TEXT,
    author TEXT,
    published_at TEXT,
    fetched_at TEXT DEFAULT (datetime('now')),
    raw_text TEXT,
    triage_summary TEXT,
    triage_score REAL,
    status TEXT DEFAULT 'new'
);

CREATE VIRTUAL TABLE IF NOT EXISTS items_fts
    USING fts5(title, raw_text, content='items', content_rowid='id');

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    item_id INTEGER REFERENCES items(id),
    chunk_index INTEGER,
    text TEXT,
    embedding BLOB
);

CREATE TABLE IF NOT EXISTS dossiers (
    topic_id INTEGER PRIMARY KEY REFERENCES topics(id),
    content TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS theses (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER REFERENCES topics(id),
    statement TEXT NOT NULL,
    rationale TEXT,
    confidence REAL,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS thesis_updates (
    id INTEGER PRIMARY KEY,
    thesis_id INTEGER REFERENCES theses(id),
    change TEXT NOT NULL,
    confidence_before REAL,
    confidence_after REAL,
    triggered_by_item_id INTEGER REFERENCES items(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER REFERENCES topics(id),
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    importance INTEGER DEFAULT 2,
    source_item_ids TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts
    USING fts5(content, content='observations', content_rowid='id');

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    report_date TEXT UNIQUE,
    digest_text TEXT,
    full_markdown TEXT,
    delivered_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS items_fts_ai
    AFTER INSERT ON items BEGIN
        INSERT INTO items_fts(rowid, title, raw_text)
        VALUES (new.id, new.title, new.raw_text);
    END;

CREATE TRIGGER IF NOT EXISTS items_fts_au
    AFTER UPDATE ON items BEGIN
        INSERT INTO items_fts(items_fts, rowid, title, raw_text)
        VALUES ('delete', old.id, old.title, old.raw_text);
        INSERT INTO items_fts(rowid, title, raw_text)
        VALUES (new.id, new.title, new.raw_text);
    END;

CREATE TRIGGER IF NOT EXISTS items_fts_ad
    AFTER DELETE ON items BEGIN
        INSERT INTO items_fts(items_fts, rowid, title, raw_text)
        VALUES ('delete', old.id, old.title, old.raw_text);
    END;

CREATE TRIGGER IF NOT EXISTS observations_fts_ai
    AFTER INSERT ON observations BEGIN
        INSERT INTO observations_fts(rowid, content)
        VALUES (new.id, new.content);
    END;

CREATE TRIGGER IF NOT EXISTS observations_fts_au
    AFTER UPDATE ON observations BEGIN
        INSERT INTO observations_fts(observations_fts, rowid, content)
        VALUES ('delete', old.id, old.content);
        INSERT INTO observations_fts(rowid, content)
        VALUES (new.id, new.content);
    END;

CREATE TRIGGER IF NOT EXISTS observations_fts_ad
    AFTER DELETE ON observations BEGIN
        INSERT INTO observations_fts(observations_fts, rowid, content)
        VALUES ('delete', old.id, old.content);
    END;
"""


def init_db(path: str = "data/analyst.db") -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")

    for statement in _DDL.strip().split(";"):
        s = statement.strip()
        if s:
            conn.execute(s)

    for statement in _FTS_TRIGGERS.strip().split(";"):
        s = statement.strip()
        if s:
            conn.execute(s)

    conn.commit()
    return conn
```

### Step 1.4 — Implement `tests/conftest.py`

- [ ] Replace the stub with:

```python
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from perpetual_analyst.analyst.schemas import NewObservation, ThesisUpdate, TopicAnalysis
from perpetual_analyst.store.db import init_db
from perpetual_analyst.store.models import Item, Topic


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = init_db(":memory:")
    # Insert default user so FK constraints are satisfied
    conn.execute("INSERT INTO users (id, telegram_chat_id) VALUES (1, 'test-chat-id')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def sample_topic(db: sqlite3.Connection) -> Topic:
    cur = db.execute(
        "INSERT INTO topics (user_id, slug, name, brief) VALUES (1, 'test-topic', 'Test Topic', 'Track test things')"
    )
    db.commit()
    row = db.execute("SELECT * FROM topics WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Topic.from_row(row)


@pytest.fixture
def sample_source(db: sqlite3.Connection) -> int:
    cur = db.execute("INSERT INTO sources (type, name) VALUES ('inbox', 'Test Inbox')")
    db.commit()
    return cur.lastrowid


@pytest.fixture
def sample_items(db: sqlite3.Connection, sample_topic: Topic, sample_source: int) -> list[Item]:
    items = [
        ("hash_a", "Item Alpha", "Alpha text about AI safety"),
        ("hash_b", "Item Beta", "Beta text about compute scaling"),
        ("hash_c", "Item Gamma", "Gamma text about open weights"),
    ]
    result = []
    for content_hash, title, raw_text in items:
        cur = db.execute(
            "INSERT INTO items (source_id, content_hash, title, raw_text) VALUES (?, ?, ?, ?)",
            (sample_source, content_hash, title, raw_text),
        )
        db.commit()
        row = db.execute("SELECT * FROM items WHERE id = ?", (cur.lastrowid,)).fetchone()
        result.append(Item.from_row(row))
    return result


@pytest.fixture
def mock_openrouter(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    canned_result = TopicAnalysis(
        report_section_markdown="## Test Topic\n\nNothing significant today.",
        new_observations=[
            NewObservation(kind="signal", content="Test signal observed.", importance=2, source_item_ids=[1])
        ],
        thesis_updates=[],
        dossier_edits=None,
        open_questions=["What happens next?"],
        watch_next=["Watch source X"],
        nothing_significant=False,
    )

    usage_mock = MagicMock()
    usage_mock.total_tokens = 1234

    response_mock = MagicMock()
    response_mock.parsed = canned_result
    response_mock.usage = usage_mock

    client_mock = MagicMock()
    client_mock.beta.chat.completions.parse.return_value = response_mock

    import perpetual_analyst.analyst.agent as agent_module
    monkeypatch.setattr(agent_module, "make_client", lambda: client_mock)

    return client_mock
```

### Step 1.5 — Create `config/settings.yaml`

- [ ] Create `config/settings.yaml`:

```yaml
models:
  analyst:
    id: "anthropic/claude-opus-4-8"
    thinking: true
  triage:
    id: "deepseek/deepseek-v4-flash"
    thinking: false
```

### Step 1.6 — Implement `src/perpetual_analyst/config.py`

- [ ] Create `src/perpetual_analyst/config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
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
```

### Step 1.7 — Run tests and verify all pass

- [ ] Run:

```
.venv\Scripts\pytest tests/test_store.py -v
```

Expected output:
```
tests/test_store.py::test_init_db_creates_all_tables PASSED
tests/test_store.py::test_init_db_creates_fts_tables PASSED
tests/test_store.py::test_fts_syncs_on_item_insert PASSED
tests/test_store.py::test_fts_syncs_on_item_delete PASSED
tests/test_store.py::test_content_hash_deduplication PASSED
tests/test_store.py::test_foreign_keys_enabled PASSED
```

### Step 1.8 — Pre-commit and commit

- [ ] Run pre-commit:

```
.venv\Scripts\pre-commit run --all-files
```

- [ ] Commit:

```
git add src/perpetual_analyst/store/db.py src/perpetual_analyst/store/models.py
git add src/perpetual_analyst/config.py config/settings.yaml
git add tests/conftest.py tests/test_store.py
git commit -m "feat: DB layer — schema, FTS5 triggers, row models, settings loader"
```

- [ ] Attach git note:

```
git notes add -m "Task: Task 1 — DB layer
Summary: Full SQLite DDL, FTS5 virtual tables + sync triggers, dataclass row models, Settings loader
Docs: docs/database.md
TODO: Phase 1 Task 1
Validation: ruff, ruff-format, pytest tests/test_store.py" $(git log -1 --format="%H")
```

---

## Task 2 — Memory Module *(parallel after Task 1)*

**Files:**
- Implement: `src/perpetual_analyst/analyst/memory.py`
- Create: `tests/test_memory.py`

### Step 2.1 — Write failing tests

- [ ] Create `tests/test_memory.py`:

```python
from __future__ import annotations

import sqlite3

import pytest

from perpetual_analyst.analyst.memory import (
    CHARS_PER_TOKEN,
    apply_all_memory_writes,
    build_memory_context,
    get_active_observations,
    get_active_theses,
    get_dossier,
    insert_observation,
    update_dossier,
)
from perpetual_analyst.analyst.schemas import NewObservation, ThesisUpdate, TopicAnalysis
from perpetual_analyst.store.models import Observation, Thesis


def test_dossier_roundtrip(db: sqlite3.Connection, sample_topic) -> None:
    assert get_dossier(sample_topic.id, db) is None
    update_dossier(sample_topic.id, "## Understanding\nAI is accelerating.", db)
    db.commit()
    assert get_dossier(sample_topic.id, db) == "## Understanding\nAI is accelerating."


def test_dossier_upsert(db: sqlite3.Connection, sample_topic) -> None:
    update_dossier(sample_topic.id, "first", db)
    db.commit()
    update_dossier(sample_topic.id, "second", db)
    db.commit()
    assert get_dossier(sample_topic.id, db) == "second"


def test_insert_observation(db: sqlite3.Connection, sample_topic) -> None:
    obs = NewObservation(kind="signal", content="GPT-5 rumoured.", importance=3, source_item_ids=[1, 2])
    row_id = insert_observation(sample_topic.id, obs, db)
    db.commit()
    assert row_id > 0
    active = get_active_observations(sample_topic.id, db)
    assert len(active) == 1
    assert active[0].content == "GPT-5 rumoured."
    assert active[0].importance == 3


def test_build_memory_context_respects_budget(db: sqlite3.Connection, sample_topic) -> None:
    # Insert 10 observations with long content
    for i in range(10):
        obs = NewObservation(
            kind="fact",
            content="A" * 200,  # 200 chars each
            importance=2,
            source_item_ids=[],
        )
        insert_observation(sample_topic.id, obs, db)
    db.commit()

    # Budget of 100 tokens = 400 chars — fits ~2 observations (each ~215 chars with prefix)
    context = build_memory_context(sample_topic.id, db, token_budget=100)
    assert len(context) <= 100 * CHARS_PER_TOKEN + 50  # small slack for prefix text


def test_build_memory_context_sorts_by_importance(db: sqlite3.Connection, sample_topic) -> None:
    insert_observation(sample_topic.id, NewObservation(kind="fact", content="Minor note.", importance=1), db)
    insert_observation(sample_topic.id, NewObservation(kind="signal", content="Critical signal.", importance=3), db)
    insert_observation(sample_topic.id, NewObservation(kind="pattern", content="Notable pattern.", importance=2), db)
    db.commit()

    context = build_memory_context(sample_topic.id, db, token_budget=10000)
    critical_pos = context.index("Critical signal.")
    notable_pos = context.index("Notable pattern.")
    minor_pos = context.index("Minor note.")
    assert critical_pos < notable_pos < minor_pos


def test_apply_thesis_update_creates_new(db: sqlite3.Connection, sample_topic) -> None:
    from perpetual_analyst.analyst.memory import apply_thesis_update

    update = ThesisUpdate(
        thesis_id=None,
        statement="Open weights will reach frontier parity.",
        confidence=0.7,
        change_rationale="Three strong signals this week.",
        new_status="active",
    )
    apply_thesis_update(update, sample_topic.id, db)
    db.commit()

    theses = get_active_theses(sample_topic.id, db)
    assert len(theses) == 1
    assert theses[0].confidence == 0.7

    # Audit row must exist
    audit = db.execute("SELECT * FROM thesis_updates WHERE thesis_id = ?", (theses[0].id,)).fetchall()
    assert len(audit) == 1


def test_apply_thesis_update_writes_audit_trail(db: sqlite3.Connection, sample_topic) -> None:
    from perpetual_analyst.analyst.memory import apply_thesis_update

    # Create thesis
    create = ThesisUpdate(thesis_id=None, statement="S", confidence=0.5, change_rationale="init", new_status="active")
    apply_thesis_update(create, sample_topic.id, db)
    db.commit()
    thesis_id = get_active_theses(sample_topic.id, db)[0].id

    # Revise thesis
    revise = ThesisUpdate(thesis_id=thesis_id, statement="S revised", confidence=0.8, change_rationale="new evidence", new_status="active")
    apply_thesis_update(revise, sample_topic.id, db)
    db.commit()

    audit_rows = db.execute("SELECT * FROM thesis_updates WHERE thesis_id = ?", (thesis_id,)).fetchall()
    assert len(audit_rows) == 2
    last = audit_rows[-1]
    assert last["confidence_before"] == pytest.approx(0.5)
    assert last["confidence_after"] == pytest.approx(0.8)


def test_apply_all_memory_writes_is_atomic(db: sqlite3.Connection, sample_topic) -> None:
    result = TopicAnalysis(
        report_section_markdown="# Section",
        new_observations=[
            NewObservation(kind="fact", content="Atomic fact.", importance=2, source_item_ids=[])
        ],
        thesis_updates=[
            ThesisUpdate(thesis_id=None, statement="Atomic thesis.", confidence=0.6, change_rationale="test", new_status="active")
        ],
        dossier_edits="Updated dossier content.",
        open_questions=[],
        watch_next=[],
        nothing_significant=False,
    )
    apply_all_memory_writes(sample_topic.id, result, db)

    assert len(get_active_observations(sample_topic.id, db)) == 1
    assert len(get_active_theses(sample_topic.id, db)) == 1
    assert get_dossier(sample_topic.id, db) == "Updated dossier content."
```

- [ ] Run to confirm failures:

```
.venv\Scripts\pytest tests/test_memory.py -v 2>&1 | head -20
```

Expected: `ImportError` — `memory` functions not implemented.

### Step 2.2 — Implement `analyst/memory.py`

- [ ] Replace stub with:

```python
from __future__ import annotations

import json
import sqlite3

from perpetual_analyst.analyst.schemas import NewObservation, ThesisUpdate, TopicAnalysis
from perpetual_analyst.store.models import Observation, Thesis

CHARS_PER_TOKEN: int = 4


def get_dossier(topic_id: int, conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT content FROM dossiers WHERE topic_id = ?", (topic_id,)
    ).fetchone()
    return row["content"] if row else None


def update_dossier(topic_id: int, content: str, conn: sqlite3.Connection) -> None:
    conn.execute(
        """INSERT INTO dossiers (topic_id, content, updated_at)
           VALUES (?, ?, datetime('now'))
           ON CONFLICT(topic_id) DO UPDATE
           SET content = excluded.content, updated_at = excluded.updated_at""",
        (topic_id, content),
    )


def get_active_observations(topic_id: int, conn: sqlite3.Connection) -> list[Observation]:
    rows = conn.execute(
        """SELECT * FROM observations
           WHERE topic_id = ? AND status = 'active'
           ORDER BY importance DESC, created_at DESC""",
        (topic_id,),
    ).fetchall()
    return [Observation.from_row(row) for row in rows]


def insert_observation(topic_id: int, obs: NewObservation, conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        """INSERT INTO observations (topic_id, kind, content, importance, source_item_ids)
           VALUES (?, ?, ?, ?, ?)""",
        (topic_id, obs.kind, obs.content, obs.importance, json.dumps(obs.source_item_ids)),
    )
    return cur.lastrowid


def get_active_theses(topic_id: int, conn: sqlite3.Connection) -> list[Thesis]:
    rows = conn.execute(
        "SELECT * FROM theses WHERE topic_id = ? AND status = 'active'",
        (topic_id,),
    ).fetchall()
    return [Thesis.from_row(row) for row in rows]


def apply_thesis_update(update: ThesisUpdate, topic_id: int, conn: sqlite3.Connection) -> None:
    if update.thesis_id is None:
        cur = conn.execute(
            """INSERT INTO theses (topic_id, statement, rationale, confidence, status)
               VALUES (?, ?, ?, ?, ?)""",
            (topic_id, update.statement, update.change_rationale, update.confidence, update.new_status),
        )
        thesis_id = cur.lastrowid
        conn.execute(
            """INSERT INTO thesis_updates (thesis_id, change, confidence_before, confidence_after)
               VALUES (?, ?, ?, ?)""",
            (thesis_id, f"Created: {update.change_rationale}", None, update.confidence),
        )
    else:
        row = conn.execute(
            "SELECT confidence FROM theses WHERE id = ?", (update.thesis_id,)
        ).fetchone()
        confidence_before = row["confidence"] if row else None
        conn.execute(
            """UPDATE theses
               SET statement = ?, confidence = ?, status = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (update.statement, update.confidence, update.new_status, update.thesis_id),
        )
        conn.execute(
            """INSERT INTO thesis_updates (thesis_id, change, confidence_before, confidence_after)
               VALUES (?, ?, ?, ?)""",
            (update.thesis_id, update.change_rationale, confidence_before, update.confidence),
        )


def build_memory_context(
    topic_id: int, conn: sqlite3.Connection, token_budget: int = 3000
) -> str:
    observations = get_active_observations(topic_id, conn)
    char_budget = token_budget * CHARS_PER_TOKEN
    parts: list[str] = []
    used = 0
    for obs in observations:
        line = f"[{obs.kind.upper()}] (importance {obs.importance}) {obs.content}"
        if used + len(line) + 1 > char_budget:
            break
        parts.append(line)
        used += len(line) + 1
    return "\n".join(parts)


def apply_all_memory_writes(
    topic_id: int, result: TopicAnalysis, conn: sqlite3.Connection
) -> None:
    with conn:
        for obs in result.new_observations:
            insert_observation(topic_id, obs, conn)
        for update in result.thesis_updates:
            apply_thesis_update(update, topic_id, conn)
        if result.dossier_edits is not None:
            update_dossier(topic_id, result.dossier_edits, conn)
```

### Step 2.3 — Run tests, pre-commit, commit

- [ ] Run:

```
.venv\Scripts\pytest tests/test_memory.py -v
```

Expected: all 8 tests PASSED.

- [ ] Pre-commit + commit:

```
.venv\Scripts\pre-commit run --all-files
git add src/perpetual_analyst/analyst/memory.py tests/test_memory.py
git commit -m "feat: memory module — dossier/observation/thesis CRUD + build_memory_context"
```

- [ ] Git note:

```
git notes add -m "Task: Task 2 — Memory module
Summary: CRUD for dossier, observations, theses; audit trail; budget-truncating context builder; atomic apply_all_memory_writes
Docs: docs/database.md
TODO: Phase 1 Task 2
Validation: ruff, ruff-format, pytest tests/test_memory.py" $(git log -1 --format="%H")
```

---

## Task 3 — Finalize System Prompt *(parallel after Task 1)*

**Files:**
- Finalize: `src/perpetual_analyst/analyst/prompts/analyst_system.md`

### Step 3.1 — Replace draft with final prompt

- [ ] Overwrite `src/perpetual_analyst/analyst/prompts/analyst_system.md` with:

```markdown
# Perpetual Analyst — System Prompt

You are a personal intelligence analyst with persistent memory. You maintain an evolving understanding of each topic you track. Your output is a structured JSON object — not prose — but the analysis inside it must reflect genuine judgment.

## What you receive each run

Your user message contains these sections in order:

1. **Topic brief** — what the user cares about; your analytical mandate
2. **Dossier** — your current standing understanding of the topic (you wrote this)
3. **Active theses** — positions you hold, with confidence scores you assigned
4. **Yesterday's report section** — what you told the user last time
5. **Prior observations** — your working memory, sorted by importance
6. **Today's items** — new documents, each tagged `[item:N]`

## 12 Behavioral rules

1. **Summarize selectively.** Most items deserve one line or silence. Cover what's new at the depth it deserves.

2. **Judge importance explicitly.** State which development is most important and argue why, tied to the topic brief.

3. **Report the delta.** The unit of analysis is change: what is different from yesterday's understanding. Do not restate what you already reported unless its meaning changed.

4. **Connect to memory.** Tie new items to prior observations and theses by ID: "this confirms [obs:91] from May 28" or "this pressures thesis 3."

5. **Touch every active thesis.** Each must be confirmed, pressured, or noted as unaffected. Confidence moves require a stated reason logged in `thesis_updates`.

6. **Spot emerging trends.** When ≥3 related signals accumulate, propose a `pattern` observation or a new thesis.

7. **Label epistemic categories.** Distinguish: **Fact** (reported by source) / **Read** (analyst inference) / **Speculation** (uncertain extrapolation).

8. **Surface contradictions.** When sources conflict, report both sides. Do not average them away.

9. **Explain so-what.** Every "important" item must carry an implication tied to the topic brief.

10. **Maintain open questions.** Questions persist until answered or explicitly retired. Notice when today's items answer one.

11. **Recommend monitoring.** List what to watch next. Flag if a topic lacks a reliable primary source.

12. **Be quiet when nothing happened.** Set `nothing_significant: true` when today's items contain nothing worth reporting. This is the most important rule. A daily analyst that manufactures significance trains the user to ignore it.

## Voice

First person. Confident. Terse. Explicit about memory: "I noted on May 14 that…". Conservative about novelty: three weak signals ≠ a trend. Record misses: a retired thesis is a learning event.

## Output schema

Return a single JSON object matching this schema exactly. Do not wrap it in markdown code blocks.

```json
{
  "report_section_markdown": "string — the user-facing analysis. Use [item:N] tags for citations. Empty string if nothing_significant is true.",
  "new_observations": [
    {
      "kind": "fact | signal | pattern | contradiction | question",
      "content": "string",
      "importance": 1,
      "source_item_ids": [1, 2]
    }
  ],
  "thesis_updates": [
    {
      "thesis_id": null,
      "statement": "string",
      "confidence": 0.7,
      "change_rationale": "string — why confidence changed or why thesis is new",
      "new_status": "active | confirmed | revised | retired"
    }
  ],
  "dossier_edits": "string or null — full replacement dossier text, null if unchanged",
  "open_questions": ["string"],
  "watch_next": ["string"],
  "nothing_significant": false
}
```

`thesis_id` is `null` to propose a new thesis; provide the integer ID to update an existing one.
```

### Step 3.2 — Commit

- [ ] Pre-commit + commit:

```
.venv\Scripts\pre-commit run --all-files
git add src/perpetual_analyst/analyst/prompts/analyst_system.md
git commit -m "docs: finalize analyst system prompt with context template and JSON schema"
```

- [ ] Git note:

```
git notes add -m "Task: Task 3 — System prompt
Summary: Finalized 12 behavioral rules, context structure template, output JSON schema guidance
Docs: N/A
TODO: Phase 1 Task 3
Validation: manual review" $(git log -1 --format="%H")
```

---

## Task 4 — Analyst Agent Call *(after Tasks 2 + 3)*

**Files:**
- Implement: `src/perpetual_analyst/analyst/agent.py`
- Create: `tests/test_agent.py`

### Step 4.1 — Write failing tests

- [ ] Create `tests/test_agent.py`:

```python
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from perpetual_analyst.analyst.agent import assemble_context, load_system_prompt, run_topic
from perpetual_analyst.analyst.memory import get_active_observations, get_dossier, get_active_theses
from perpetual_analyst.analyst.schemas import TopicAnalysis
from perpetual_analyst.config import Settings, ModelConfig
from perpetual_analyst.store.models import Topic


@pytest.fixture
def settings() -> Settings:
    return Settings(
        analyst=ModelConfig(id="anthropic/claude-opus-4-8", thinking=True),
        triage=ModelConfig(id="deepseek/deepseek-v4-flash", thinking=False),
    )


def test_load_system_prompt_returns_string() -> None:
    prompt = load_system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 100
    assert "nothing_significant" in prompt


def test_assemble_context_returns_two_messages(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings
) -> None:
    prompt = load_system_prompt()
    messages = assemble_context(sample_topic, sample_items, db, prompt, settings)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_assemble_context_system_is_stable_prefix(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings
) -> None:
    prompt = load_system_prompt()
    messages = assemble_context(sample_topic, sample_items, db, prompt, settings)
    assert messages[0]["content"] == prompt


def test_assemble_context_includes_item_tags(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings
) -> None:
    prompt = load_system_prompt()
    messages = assemble_context(sample_topic, sample_items, db, prompt, settings)
    user_content = messages[1]["content"]
    for item in sample_items:
        assert f"[item:{item.id}]" in user_content


def test_assemble_context_includes_topic_brief(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings
) -> None:
    prompt = load_system_prompt()
    messages = assemble_context(sample_topic, sample_items, db, prompt, settings)
    assert sample_topic.brief in messages[1]["content"]


def test_run_topic_dry_run_returns_none(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings,
    mock_openrouter: MagicMock, capsys
) -> None:
    result = run_topic(sample_topic, sample_items, db, mock_openrouter, settings, dry_run=True)
    assert result is None
    mock_openrouter.beta.chat.completions.parse.assert_not_called()


def test_run_topic_dry_run_prints_messages(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings,
    mock_openrouter: MagicMock, capsys
) -> None:
    run_topic(sample_topic, sample_items, db, mock_openrouter, settings, dry_run=True)
    captured = capsys.readouterr()
    assert "SYSTEM" in captured.out
    assert "USER" in captured.out


def test_run_topic_commits_memory_writes(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings,
    mock_openrouter: MagicMock
) -> None:
    run_topic(sample_topic, sample_items, db, mock_openrouter, settings, dry_run=False)
    observations = get_active_observations(sample_topic.id, db)
    assert len(observations) == 1
    assert observations[0].content == "Test signal observed."


def test_run_topic_passes_thinking_when_configured(
    db: sqlite3.Connection, sample_topic: Topic, sample_items,
    mock_openrouter: MagicMock
) -> None:
    settings_with_thinking = Settings(
        analyst=ModelConfig(id="anthropic/claude-opus-4-8", thinking=True),
        triage=ModelConfig(id="deepseek/deepseek-v4-flash", thinking=False),
    )
    run_topic(sample_topic, sample_items, db, mock_openrouter, settings_with_thinking)
    call_kwargs = mock_openrouter.beta.chat.completions.parse.call_args
    extra_body = call_kwargs.kwargs.get("extra_body", {})
    assert extra_body.get("thinking") == {"type": "adaptive"}


def test_run_topic_no_thinking_when_disabled(
    db: sqlite3.Connection, sample_topic: Topic, sample_items,
    mock_openrouter: MagicMock
) -> None:
    settings_no_thinking = Settings(
        analyst=ModelConfig(id="some-model", thinking=False),
        triage=ModelConfig(id="deepseek/deepseek-v4-flash", thinking=False),
    )
    run_topic(sample_topic, sample_items, db, mock_openrouter, settings_no_thinking)
    call_kwargs = mock_openrouter.beta.chat.completions.parse.call_args
    extra_body = call_kwargs.kwargs.get("extra_body", {})
    assert "thinking" not in extra_body
```

- [ ] Run to confirm failures:

```
.venv\Scripts\pytest tests/test_agent.py -v 2>&1 | head -20
```

Expected: ImportError — `agent` functions not implemented.

### Step 4.2 — Implement `analyst/agent.py`

- [ ] Replace stub with:

```python
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import openai
from dotenv import load_dotenv

from perpetual_analyst.analyst.memory import (
    CHARS_PER_TOKEN,
    apply_all_memory_writes,
    build_memory_context,
    get_active_theses,
    get_dossier,
)
from perpetual_analyst.analyst.schemas import TopicAnalysis
from perpetual_analyst.config import Settings
from perpetual_analyst.store.models import Item, Topic

if TYPE_CHECKING:
    import sqlite3

load_dotenv()

_system_prompt: str | None = None
_PROMPT_PATH = Path(__file__).parent / "prompts" / "analyst_system.md"


def load_system_prompt() -> str:
    global _system_prompt
    if _system_prompt is None:
        _system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    return _system_prompt


def make_client() -> openai.OpenAI:
    return openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )


def assemble_context(
    topic: Topic,
    items: list[Item],
    conn: sqlite3.Connection,
    system_prompt: str,
    settings: Settings,
) -> list[dict]:
    dossier = get_dossier(topic.id, conn) or "(no dossier yet)"
    theses = get_active_theses(topic.id, conn)
    observations_text = build_memory_context(topic.id, conn, token_budget=3000)

    row = conn.execute(
        "SELECT full_markdown FROM reports "
        "WHERE report_date < date('now') ORDER BY report_date DESC LIMIT 1"
    ).fetchone()
    yesterday_section = row["full_markdown"] if row else "(no prior report)"

    theses_text = (
        "\n".join(f"[thesis:{t.id}] (confidence {t.confidence:.2f}) {t.statement}" for t in theses)
        or "(no active theses)"
    )

    items_text = "\n\n".join(
        f"[item:{item.id}] {item.title or '(untitled)'}\n{item.raw_text or '(no text)'}"
        for item in items
    ) or "(no new items today)"

    user_content = (
        f"## Topic brief\n{topic.brief or '(no brief)'}\n\n"
        f"## Dossier\n{dossier}\n\n"
        f"## Active theses\n{theses_text}\n\n"
        f"## Yesterday's report section\n{yesterday_section}\n\n"
        f"## Prior observations\n{observations_text or '(no prior observations)'}\n\n"
        f"## Today's items\n{items_text}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def run_topic(
    topic: Topic,
    items: list[Item],
    conn: sqlite3.Connection,
    client: openai.OpenAI,
    settings: Settings,
    dry_run: bool = False,
) -> TopicAnalysis | None:
    system_prompt = load_system_prompt()
    messages = assemble_context(topic, items, conn, system_prompt, settings)

    if dry_run:
        for msg in messages:
            print(f"[{msg['role'].upper()}]\n{msg['content']}\n{'=' * 60}")
        return None

    extra = {"thinking": {"type": "adaptive"}} if settings.analyst.thinking else {}
    response = client.beta.chat.completions.parse(
        model=settings.analyst.id,
        messages=messages,
        response_format=TopicAnalysis,
        extra_body=extra,
    )

    result: TopicAnalysis = response.parsed
    used = response.usage.total_tokens if response.usage else len(str(messages)) // CHARS_PER_TOKEN
    print(f"[agent] topic={topic.slug} tokens={used} nothing_significant={result.nothing_significant}")

    apply_all_memory_writes(topic.id, result, conn)
    return result
```

### Step 4.3 — Run tests, pre-commit, commit

- [ ] Run:

```
.venv\Scripts\pytest tests/test_agent.py -v
```

Expected: all 9 tests PASSED.

- [ ] Run full suite to verify no regressions:

```
.venv\Scripts\pytest -v
```

- [ ] Pre-commit + commit:

```
.venv\Scripts\pre-commit run --all-files
git add src/perpetual_analyst/analyst/agent.py tests/test_agent.py
git commit -m "feat: analyst agent — context assembly, OpenRouter call, dry-run, memory commit"
```

- [ ] Git note:

```
git notes add -m "Task: Task 4 — Analyst agent call
Summary: assemble_context in caching order, OpenRouter parse call, adaptive thinking flag, dry-run, transactional memory writes
Docs: docs/architecture.md
TODO: Phase 1 Task 4
Validation: ruff, ruff-format, pytest" $(git log -1 --format="%H")
```

---

## Task 5 — Inbox Ingestion *(parallel after Task 1)*

**Files:**
- Implement: `src/perpetual_analyst/ingestion/inbox.py`
- Create: `tests/test_ingestion.py`

### Step 5.1 — Write failing tests

- [ ] Create `tests/test_ingestion.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from perpetual_analyst.ingestion.inbox import scan_inbox
from perpetual_analyst.store.models import Item


@pytest.fixture
def inbox_dir(tmp_path: Path, sample_topic) -> Path:
    topic_dir = tmp_path / sample_topic.slug
    topic_dir.mkdir()
    return topic_dir


def _write_file(dir_: Path, name: str, content: str) -> Path:
    p = dir_ / name
    p.write_text(content, encoding="utf-8")
    return p


def test_scan_inbox_ingests_txt_file(
    db: sqlite3.Connection, sample_topic, sample_source: int, inbox_dir: Path, monkeypatch
) -> None:
    monkeypatch.chdir(inbox_dir.parent.parent)  # set cwd to tmp_path root
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

    # First scan — inserts
    items1 = scan_inbox(sample_topic.slug, sample_topic.id, sample_source, db)
    assert len(items1) == 1

    # Re-drop same content with different filename
    (inbox_dir / ".processed").mkdir(exist_ok=True)
    _write_file(inbox_dir, "second.txt", "Identical content here.")

    # Second scan — duplicate content, should not insert again
    items2 = scan_inbox(sample_topic.slug, sample_topic.id, sample_source, db)
    assert len(items2) == 0  # rowcount == 0 means already in DB

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
```

- [ ] Run to confirm failures:

```
.venv\Scripts\pytest tests/test_ingestion.py -v 2>&1 | head -20
```

Expected: ImportError — `scan_inbox` not implemented.

### Step 5.2 — Implement `ingestion/inbox.py`

- [ ] Replace stub with:

```python
from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

from perpetual_analyst.store.models import Item


def _extract_text(path: Path) -> str | None:
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def scan_inbox(
    topic_slug: str,
    topic_id: int,
    source_id: int,
    conn: sqlite3.Connection,
) -> list[Item]:
    inbox_dir = Path("inbox") / topic_slug
    processed_dir = inbox_dir / ".processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    inserted: list[Item] = []

    if not inbox_dir.exists():
        return inserted

    for path in sorted(inbox_dir.iterdir()):
        if path.name.startswith(".") or path.is_dir():
            continue
        if path.suffix.lower() not in {".pdf", ".md", ".txt"}:
            continue

        raw_text = _extract_text(path)
        if not raw_text or not raw_text.strip():
            continue

        content_hash = hashlib.sha256(raw_text.strip().encode()).hexdigest()

        cur = conn.execute(
            """INSERT OR IGNORE INTO items (source_id, content_hash, title, raw_text)
               VALUES (?, ?, ?, ?)""",
            (source_id, content_hash, path.stem, raw_text),
        )
        conn.commit()

        dest = processed_dir / path.name
        shutil.move(str(path), str(dest))

        if cur.rowcount > 0:
            row = conn.execute(
                "SELECT * FROM items WHERE content_hash = ?", (content_hash,)
            ).fetchone()
            inserted.append(Item.from_row(row))

    return inserted
```

### Step 5.3 — Run tests, pre-commit, commit

- [ ] Run:

```
.venv\Scripts\pytest tests/test_ingestion.py -v
```

Expected: all 7 tests PASSED.

- [ ] Run full suite:

```
.venv\Scripts\pytest -v
```

Expected: all tests PASSED.

- [ ] Pre-commit + commit:

```
.venv\Scripts\pre-commit run --all-files
git add src/perpetual_analyst/ingestion/inbox.py tests/test_ingestion.py
git commit -m "feat: inbox ingestion — scan, extract, hash-dedupe, move to .processed"
```

- [ ] Git note:

```
git notes add -m "Task: Task 5 — Inbox ingestion
Summary: scan_inbox walks inbox/<slug>/, extracts txt/md/pdf, dedupes on content_hash, moves processed files
Docs: docs/architecture.md
TODO: Phase 1 Task 5
Validation: ruff, ruff-format, pytest tests/test_ingestion.py" $(git log -1 --format="%H")
```

---

## End-to-End Smoke Test

After all 5 tasks are merged to the branch, verify Phase 1 exit criterion:

- [ ] Create `inbox/test-topic/` and drop 3 `.txt` files with distinct content
- [ ] Run:

```
.venv\Scripts\python -c "
from perpetual_analyst.store.db import init_db
from perpetual_analyst.config import load_settings
from perpetual_analyst.store.models import Topic
from perpetual_analyst.ingestion.inbox import scan_inbox
from perpetual_analyst.analyst.agent import run_topic, make_client

conn = init_db()
conn.execute(\"INSERT OR IGNORE INTO users (id) VALUES (1)\")
conn.execute(\"INSERT OR IGNORE INTO topics (id, user_id, slug, name, brief) VALUES (1, 1, 'test-topic', 'Test', 'Testing')\")
conn.execute(\"INSERT OR IGNORE INTO sources (id, type, name) VALUES (1, 'inbox', 'Test Inbox')\")
conn.commit()

items = scan_inbox('test-topic', 1, 1, conn)
print(f'Ingested {len(items)} items')

topic = Topic.from_row(conn.execute('SELECT * FROM topics WHERE id = 1').fetchone())
settings = load_settings()

result = run_topic(topic, items, conn, None, settings, dry_run=True)
print('Dry-run complete — check output above for assembled context')
"
```

Expected: assembled context printed showing topic brief, dossier placeholder, items with `[item:N]` tags.
