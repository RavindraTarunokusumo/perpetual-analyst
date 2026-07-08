# Testing Guide

## Purpose

Testing includes both execution and planning. Run automated tests and use the `test-plan-writer` agent when meaningful changes need explicit coverage mapping.

## Prerequisites

- Activate the project environment: `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate`
- Run commands from repo root
- Mock OpenRouter/openai API calls — never make real API calls in tests
- Mock `telegram.Bot` — never make real Telegram calls in tests
- Use in-memory SQLite (`analyst.db` = `:memory:`) for all DB tests

## Test Layout

```
tests/
  conftest.py          # shared fixtures (in-memory DB, mock OpenRouter client)
  test_store.py        # schema creation, FTS triggers, dedupe behavior
  test_memory.py       # dossier/observation/thesis CRUD, budget enforcement
  test_theses.py       # thesis lifecycle, ≤7 limit, stale flagging, render_thesis_fragment
  test_triage.py       # triage call structure (mocked); robust JSON extraction; chunking
  test_agent.py        # context assembly order, dry-run output, memory write transaction
  test_ingestion.py    # inbox file loading, hash dedupe, RSS parsing (undated entries)
  test_retrieval.py    # FTS search helpers, recency weighting, exclude_ids
  test_report.py       # citation rendering, report assembly
  test_delivery.py     # Telegram send + retry logic (mocked)
  test_discovery.py    # source discovery and provider seam
  test_quality.py      # source quality scoring
  test_source_candidates.py # approval/dismissal and SSRF-safe URL validation
  test_web_ui.py       # local dashboard rendering and POST actions
  test_embeddings.py   # optional embeddings gate
```

## Core Fixtures (`conftest.py`)

```python
@pytest.fixture
def db():
    """Fresh in-memory SQLite DB with full schema."""
    conn = init_db(":memory:")
    yield conn
    conn.close()

@pytest.fixture
def mock_openai(monkeypatch):
    """Stub openai.OpenAI client to return a canned TopicAnalysis (openai SDK via OpenRouter)."""
    ...
```

## Running Tests

All unit tests (smoke excluded by default):
```bash
PYTHONPATH=src pytest
```

One file:
```bash
PYTHONPATH=src pytest tests/test_memory.py
```

One test:
```bash
PYTHONPATH=src pytest tests/test_memory.py::test_budget_truncation -v
```

Stop on first failure:
```bash
PYTHONPATH=src pytest -x
```

By keyword:
```bash
PYTHONPATH=src pytest -k "thesis"
```

## Validation Workflow

Default sequence before every commit:

```bash
ruff check . --fix
ruff format .
PYTHONPATH=src pytest
```

## When to Invoke `test-plan-writer`

Invoke after implementation and before PR when:

- analyst behavior changed (prompt, context assembly, schema)
- memory budget logic changed
- DB schema or migration changed
- ingestion or triage logic changed
- report rendering or citation logic changed
- Telegram delivery logic changed
- source approval URL validation or Web UI routes changed
- discovery provider configuration changed
- optional embeddings gate changed

Do not invoke for docs-only or tiny localized edits.

## Coverage Expectations

For meaningful changes, cover:

- Happy path
- Failure path (API error, DB write failure, Telegram failure)
- Memory budget boundary (items at exactly N tokens, N+1 tokens)
- `nothing_significant: true` path through the whole pipeline
- Thesis ≤7 limit enforcement
- `content_hash` dedupe (same content, different URL)
- Transaction rollback on partial memory write failure
- Error isolation: one topic failing must not raise in `daily_run`

## Test Writing Rules

- Keep tests deterministic — no random data, no real API calls, no network I/O
- Use in-memory SQLite; never touch `data/analyst.db` in tests
- Mock the OpenAI client (OpenRouter) at the boundary — test context assembly and result handling separately from the API call
- Name tests by behavior: `test_memory_budget_truncates_importance_1_first`
- Assert durable outcomes: DB row counts, field values, file existence
- Never test implementation trivia (private method return values, internal variable names)
