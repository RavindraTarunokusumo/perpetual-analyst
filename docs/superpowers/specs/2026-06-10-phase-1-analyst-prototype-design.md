# Phase 1 — Analyst Prototype Design

**Date:** 2026-06-10
**Scope:** Tasks 1–5 from TODO.md — DB layer, memory module, agent call, inbox ingestion
**Branch:** `phase-1-analyst-prototype`

---

## Decisions Locked In

| # | Decision | Choice |
|---|---|---|
| 1 | Connection management | Explicit injection — every function takes `conn: sqlite3.Connection` |
| 2 | Row model types | `@dataclass` (Pydantic = LLM boundary only) |
| 3 | Token counting | Character heuristic (`len(text) // CHARS_PER_TOKEN`) for pre-call truncation; `response.usage.total_tokens` when OpenRouter returns it, heuristic fallback otherwise |
| 4 | Model API | OpenRouter via `openai` SDK (`base_url="https://openrouter.ai/api/v1"`) for all calls |
| 5 | Adaptive thinking | Injected via `extra_body={"thinking": {"type": "adaptive"}}` when `model_config.thinking is True` |
| 6 | Model specification | All model IDs and flags live in `config/settings.yaml`; loaded once into a `Settings` dataclass |
| 7 | Default analyst model | `anthropic/claude-opus-4-8` |
| 8 | Default triage model | `deepseek/deepseek-v4-flash` |
| 9 | Processed inbox files | Move to `inbox/<slug>/.processed/` after confirmed DB insert |

---

## Module Interfaces

### `store/db.py`

```python
def init_db(path: str = "data/analyst.db") -> sqlite3.Connection
```

- Creates parent directory if missing
- Runs full DDL (`CREATE TABLE IF NOT EXISTS`) for all tables from SPEC §5
- Creates FTS5 virtual tables: `items_fts`, `observations_fts`
- Creates sync triggers (`AFTER INSERT/UPDATE/DELETE`) for both FTS tables
- Enables `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON`
- Returns the open connection

### `store/models.py`

One `@dataclass` per table: `User`, `Topic`, `Source`, `TopicSource`, `Item`, `Chunk`, `Dossier`, `Thesis`, `ThesisUpdate`, `Observation`, `Report`.

Each has a `from_row(row: sqlite3.Row) -> Self` classmethod.

### `src/perpetual_analyst/config.py` (new flat module — not a sub-package)

```python
@dataclass
class ModelConfig:
    id: str
    thinking: bool = False

@dataclass
class Settings:
    analyst: ModelConfig
    triage: ModelConfig

def load_settings(path: str = "config/settings.yaml") -> Settings
```

### `config/settings.yaml` (new file)

```yaml
models:
  analyst:
    id: "anthropic/claude-opus-4-8"
    thinking: true
  triage:
    id: "deepseek/deepseek-v4-flash"
    thinking: false
```

### `analyst/memory.py`

```python
CHARS_PER_TOKEN: int = 4

def get_dossier(topic_id: int, conn: sqlite3.Connection) -> str | None
def update_dossier(topic_id: int, content: str, conn: sqlite3.Connection) -> None
def get_active_observations(topic_id: int, conn: sqlite3.Connection) -> list[Observation]
def insert_observation(topic_id: int, obs: NewObservation, conn: sqlite3.Connection) -> int
def get_active_theses(topic_id: int, conn: sqlite3.Connection) -> list[Thesis]
def apply_thesis_update(update: ThesisUpdate, topic_id: int, conn: sqlite3.Connection) -> None
    # writes thesis_updates audit row in the same transaction; never silently edits a thesis
def build_memory_context(topic_id: int, conn: sqlite3.Connection, token_budget: int = 3000) -> str
    # sorts observations: importance DESC, created_at DESC
    # truncates at token_budget * CHARS_PER_TOKEN characters
    # returns formatted text block ready for prompt injection
def apply_all_memory_writes(topic_id: int, result: TopicAnalysis, conn: sqlite3.Connection) -> None
    # single `with conn:` transaction:
    #   1. insert each new_observation
    #   2. apply each thesis_update (with audit row)
    #   3. update dossier if dossier_edits is not None
```

### `analyst/agent.py`

```python
def load_system_prompt() -> str
    # reads analyst_system.md once; cached in module-level variable

def make_client() -> openai.OpenAI
    # openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])

def assemble_context(
    topic: Topic,
    items: list[Item],
    conn: sqlite3.Connection,
    system_prompt: str,
    settings: Settings,
) -> list[dict]
    # returns OpenAI chat messages list in caching-friendly order:
    #   system: system_prompt
    #   user:   topic brief | dossier | active theses | last 7 days digests
    #           | yesterday's section (query reports WHERE report_date < today ORDER BY report_date DESC LIMIT 1)
    #           | observations (budgeted) | today's items

def run_topic(
    topic: Topic,
    items: list[Item],
    conn: sqlite3.Connection,
    client: openai.OpenAI,
    settings: Settings,
    dry_run: bool = False,
) -> TopicAnalysis | None
    # dry_run=True: prints assembled messages, returns None (no API call, no DB writes)
    # on success: commits all memory writes transactionally, logs token usage
    # on API error: logs and re-raises (caller handles per-topic isolation)
    # token tracking:
    #   used = response.usage.total_tokens if response.usage else len(text) // CHARS_PER_TOKEN
```

Adaptive thinking injection:
```python
extra = {"thinking": {"type": "adaptive"}} if settings.analyst.thinking else {}
response = client.beta.chat.completions.parse(
    model=settings.analyst.id,
    messages=messages,
    response_format=TopicAnalysis,
    extra_body=extra,
)
```

### `ingestion/inbox.py`

```python
def scan_inbox(
    topic_slug: str,
    topic_id: int,
    source_id: int,
    conn: sqlite3.Connection,
) -> list[Item]
```

- Walks `inbox/<topic_slug>/`; skips `.processed/` subdirectory
- Extracts text: `pypdf` for `.pdf`, plain `read_text()` for `.md`/`.txt`
- Computes `content_hash = sha256(raw_text.strip().encode()).hexdigest()`
- Inserts via `INSERT OR IGNORE INTO items (...) VALUES (...)` — duplicate hashes silently skip
- Moves file to `inbox/<slug>/.processed/<filename>` **only** after `cursor.rowcount > 0` (INSERT OR IGNORE: `rowcount == 0` means hash already existed — file still moves, since content is already in DB)
- Returns list of newly inserted `Item` rows

---

## Test Fixtures (`tests/conftest.py`)

```python
@pytest.fixture
def db() -> sqlite3.Connection:
    conn = init_db(":memory:")
    yield conn
    conn.close()

@pytest.fixture
def sample_topic(db) -> Topic:
    # INSERT one topic row; return Topic dataclass

@pytest.fixture
def sample_items(db, sample_topic) -> list[Item]:
    # INSERT 3 items with distinct content_hashes; return list[Item]

@pytest.fixture
def mock_openrouter(monkeypatch) -> MagicMock:
    # patches make_client() to return a MagicMock
    # mock.beta.chat.completions.parse() returns a response with:
    #   .parsed = canned TopicAnalysis
    #   .usage.total_tokens = 1234
```

---

## Error Handling

| Site | Behavior |
|---|---|
| `init_db` | Creates `data/` directory before opening file; raises on DDL failure |
| `scan_inbox` | File moves to `.processed/` only after confirmed insert; on extraction failure, logs and skips file |
| `run_topic` | API errors logged and re-raised; caller (`daily_run.py`) wraps each topic in `try/except` |
| `apply_all_memory_writes` | Single `with conn:` block — SQLite rolls back entire bundle on any exception |
| Secret loading | `OPENROUTER_API_KEY` loaded from `.env` via `python-dotenv`; never logged |

---

## Task Parallelism

```
Task 1 (store/db.py + models.py)
    └── Task 2 (memory.py)   ─┐
    └── Task 3 (prompt polish) ├── Task 4 (agent.py)
    └── Task 5 (inbox.py)    ─┘ (waits for 2 + 3)
```

Tasks 2, 3, 5 run in parallel after Task 1 lands. Task 4 starts after Tasks 2 and 3 are merged.

---

## New Files (relative to current skeleton)

| File | Status |
|---|---|
| `config/settings.yaml` | New |
| `src/perpetual_analyst/config.py` | New flat module |
| `store/db.py` | Implement (was stub) |
| `store/models.py` | Implement (was stub) |
| `analyst/memory.py` | Implement (was stub) |
| `analyst/agent.py` | Implement (was stub) |
| `ingestion/inbox.py` | Implement (was stub) |
| `tests/conftest.py` | Implement (was stub) |
| `tests/test_store.py` | New |
| `tests/test_memory.py` | New |
| `tests/test_agent.py` | New |
| `tests/test_ingestion.py` | New |
