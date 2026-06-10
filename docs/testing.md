# Testing Guide

## Purpose

Testing includes both execution and planning. Run automated tests and use the `test-plan-writer` agent when meaningful changes need explicit coverage mapping.

## Prerequisites

- Activate the project environment: `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate`
- Run commands from repo root
- Mock Anthropic API calls — never make real API calls in tests
- Mock Telegram sends
- Use in-memory SQLite (`analyst.db` = `:memory:`) for all DB tests

## Test Layout

```
tests/
  conftest.py          # shared fixtures (in-memory DB, mock anthropic client)
  test_store.py        # schema creation, FTS triggers, dedupe behavior
  test_memory.py       # dossier/observation/thesis CRUD, budget enforcement
  test_theses.py       # thesis lifecycle, ≤7 limit, stale flagging
  test_triage.py       # triage call structure (mocked)
  test_agent.py        # context assembly order, dry-run output, memory write transaction
  test_ingestion.py    # inbox file loading, hash dedupe, RSS parsing
  test_retrieval.py    # FTS search helpers, recency weighting
  test_report.py       # citation rendering, report assembly
  test_delivery.py     # Telegram send + retry logic (mocked)
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
def mock_anthropic(monkeypatch):
    """Stub client.messages.parse() to return a canned TopicAnalysis."""
    ...
```

## Running Tests

All tests:
```bash
pytest
```

One file:
```bash
pytest tests/test_memory.py
```

One test:
```bash
pytest tests/test_memory.py::test_budget_truncation -v
```

Stop on first failure:
```bash
pytest -x
```

By keyword:
```bash
pytest -k "thesis"
```

## Validation Workflow

Default sequence before every commit:

```bash
ruff check . --fix
ruff format .
pytest
```

## When to Invoke `test-plan-writer`

Invoke after implementation and before PR when:

- analyst behavior changed (prompt, context assembly, schema)
- memory budget logic changed
- DB schema or migration changed
- ingestion or triage logic changed
- report rendering or citation logic changed
- Telegram delivery logic changed

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
- Mock the Anthropic client at the boundary — test context assembly and result handling separately from the API call
- Name tests by behavior: `test_memory_budget_truncates_importance_1_first`
- Assert durable outcomes: DB row counts, field values, file existence
- Never test implementation trivia (private method return values, internal variable names)
