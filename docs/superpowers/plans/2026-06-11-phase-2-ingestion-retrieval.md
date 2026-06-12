# Phase 2 — Source Ingestion + Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement TODO Tasks 6–8.5 — thesis lifecycle helpers, RSS ingestion, triage, FTS5 retrieval wired into the analyst context, and YAML config sync + CLI — per the approved spec at `docs/superpowers/specs/2026-06-11-phase-2-ingestion-retrieval-design.md`.

**Architecture:** All DB writes follow Phase 1 patterns: `insert_item()` is the only item write path; thesis CRUD stays in `memory.py`; new modules (`theses.py`, `rss.py`, `triage.py`, `search.py`) are stateless functions taking `conn: sqlite3.Connection` explicitly. Triage and retrieval results flow into `assemble_context` in `agent.py`.

**Tech Stack:** Python 3.12, sqlite3 + FTS5, httpx + feedparser + trafilatura, openai SDK against OpenRouter (triage model `deepseek/deepseek-v4-flash` from `config/settings.yaml`), typer + pyyaml, pytest.

---

## Environment notes (read first)

- **Work in the worktree:** `C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.worktree\phase-2` (branch `phase-2-ingestion-retrieval`). All paths below are relative to it.
- **The package is NOT pip-installed.** Every pytest invocation must set `PYTHONPATH` to the worktree's `src` or tests import nothing (or the wrong tree). From the worktree root in PowerShell:
  ```powershell
  $env:PYTHONPATH = "$PWD\src"
  C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests -v
  ```
- **Pre-commit** (before each commit, from the worktree root):
  ```powershell
  C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\pre-commit run --all-files
  ```
  After Task 0 this must be green; if a hook auto-fixes a file you touched, restage and re-run.
- **GitNexus (orchestrator responsibility):** before Tasks 4 and 8 (both modify `assemble_context`), run `gitnexus_impact({target: "assemble_context", direction: "upstream"})` and report blast radius; run `gitnexus_detect_changes()` before each commit. Never rename symbols by find-and-replace.
- **One task = one commit** (Workflow Rule 1). Stage specific files only — never `git add -A`. Cross the matching TODO.md sub-item in the same commit. Attach a git note per `.github/git_notes_template.md` after each commit.
- **PowerShell multiline commit messages:** use `@'...'@` here-strings with the closing `'@` at column 0.

---

### Task 0: Lint cleanup on contact (pre-existing E402/E501)

`inbox.py` E402 and `test_ingestion.py` E501 are pre-existing failures that block `pre-commit run --all-files` for the whole session. Fix on contact (established feedback memory).

**Files:**
- Modify: `src/perpetual_analyst/ingestion/inbox.py:9-12`
- Modify: `tests/test_ingestion.py:61`

- [ ] **Step 1: Move `_SLUG_RE` below the imports in inbox.py**

Replace lines 9–12:

```python
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")

from perpetual_analyst.store.db import insert_item
from perpetual_analyst.store.models import Item
```

with:

```python
from perpetual_analyst.store.db import insert_item
from perpetual_analyst.store.models import Item

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
```

- [ ] **Step 2: Wrap the long line in tests/test_ingestion.py**

Replace:

```python
    count = db.execute("SELECT COUNT(*) FROM items WHERE source_id = ?", (sample_source,)).fetchone()[0]
```

with:

```python
    count = db.execute(
        "SELECT COUNT(*) FROM items WHERE source_id = ?", (sample_source,)
    ).fetchone()[0]
```

- [ ] **Step 3: Run pre-commit and the full test suite**

Run (from worktree root):
```powershell
C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\pre-commit run --all-files
$env:PYTHONPATH = "$PWD\src"
C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests -v
```
Expected: pre-commit all green (ruff may reformat — restage if so); all existing tests PASS.

- [ ] **Step 4: Commit**

```powershell
git add src/perpetual_analyst/ingestion/inbox.py tests/test_ingestion.py
git commit -m "chore: fix pre-existing E402/E501 lint failures on contact"
```

---

### Task 1: Thesis lifecycle regression tests (TODO 6.1, 6.2)

`apply_thesis_update` (create/revise/retire, ≤7 enforcement, audit rows) already exists in `memory.py`. These sub-items land as regression tests pinning the invariants.

**Files:**
- Create: `tests/test_theses.py`

- [ ] **Step 1: Write the regression tests**

```python
from __future__ import annotations

import pytest

from perpetual_analyst.analyst.memory import apply_thesis_update, get_active_theses
from perpetual_analyst.analyst.schemas import ThesisUpdate


def _update(
    thesis_id=None,
    statement="Open-weight models reach frontier parity",
    confidence=0.6,
    rationale="initial signal",
    status="active",
):
    return ThesisUpdate(
        thesis_id=thesis_id,
        statement=statement,
        confidence=confidence,
        change_rationale=rationale,
        new_status=status,
    )


def test_create_thesis_writes_audit_row(db, sample_topic):
    apply_thesis_update(_update(), sample_topic.id, db)
    theses = get_active_theses(sample_topic.id, db)
    assert len(theses) == 1
    audit = db.execute(
        "SELECT * FROM thesis_updates WHERE thesis_id = ?", (theses[0].id,)
    ).fetchall()
    assert len(audit) == 1
    assert audit[0]["confidence_before"] is None
    assert audit[0]["confidence_after"] == 0.6


def test_revise_thesis_logs_before_after(db, sample_topic):
    apply_thesis_update(_update(), sample_topic.id, db)
    thesis = get_active_theses(sample_topic.id, db)[0]
    apply_thesis_update(
        _update(thesis_id=thesis.id, confidence=0.8, rationale="third confirming signal"),
        sample_topic.id,
        db,
    )
    audit = db.execute(
        "SELECT * FROM thesis_updates WHERE thesis_id = ? ORDER BY id", (thesis.id,)
    ).fetchall()
    assert len(audit) == 2
    assert audit[1]["confidence_before"] == 0.6
    assert audit[1]["confidence_after"] == 0.8


def test_retire_thesis_removes_from_active(db, sample_topic):
    apply_thesis_update(_update(), sample_topic.id, db)
    thesis = get_active_theses(sample_topic.id, db)[0]
    apply_thesis_update(
        _update(thesis_id=thesis.id, status="retired", rationale="disproven by filing"),
        sample_topic.id,
        db,
    )
    assert get_active_theses(sample_topic.id, db) == []
    status = db.execute("SELECT status FROM theses WHERE id = ?", (thesis.id,)).fetchone()[
        "status"
    ]
    assert status == "retired"


def test_eighth_active_thesis_raises(db, sample_topic):
    for i in range(7):
        apply_thesis_update(_update(statement=f"Thesis {i}"), sample_topic.id, db)
    with pytest.raises(ValueError, match="limit"):
        apply_thesis_update(_update(statement="Thesis 8"), sample_topic.id, db)
```

- [ ] **Step 2: Run the tests — expect all PASS (regression of existing code)**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_theses.py -v`
Expected: 4 passed. If any fail, STOP — that's a Phase 1 invariant break; report it instead of fixing blind.

- [ ] **Step 3: Cross TODO 6.1 + 6.2 in TODO.md, commit**

```powershell
git add tests/test_theses.py TODO.md
git commit -m "test: pin thesis create/revise/retire invariants and <=7 limit"
```

---

### Task 2: `get_stale_theses` (TODO 6.3, query)

**Files:**
- Create: `src/perpetual_analyst/analyst/theses.py`
- Test: `tests/test_theses.py` (append)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_theses.py`)

```python
from perpetual_analyst.analyst.theses import get_stale_theses


def _insert_thesis(db, topic_id, statement, created_days_ago, updated_days_ago=None):
    updated_expr = (
        f"datetime('now', '-{updated_days_ago} days')" if updated_days_ago is not None else "NULL"
    )
    db.execute(
        f"""INSERT INTO theses (topic_id, statement, confidence, status, created_at, updated_at)
            VALUES (?, ?, 0.5, 'active', datetime('now', '-{created_days_ago} days'),
                    {updated_expr})""",
        (topic_id, statement),
    )
    db.commit()


def test_untouched_31_days_is_stale(db, sample_topic):
    _insert_thesis(db, sample_topic.id, "Old", created_days_ago=31)
    stale = get_stale_theses(sample_topic.id, db)
    assert [t.statement for t in stale] == ["Old"]


def test_untouched_29_days_is_not_stale(db, sample_topic):
    _insert_thesis(db, sample_topic.id, "Fresh-ish", created_days_ago=29)
    assert get_stale_theses(sample_topic.id, db) == []


def test_recent_update_overrides_old_creation(db, sample_topic):
    _insert_thesis(db, sample_topic.id, "Maintained", created_days_ago=60, updated_days_ago=5)
    assert get_stale_theses(sample_topic.id, db) == []


def test_old_update_is_stale(db, sample_topic):
    _insert_thesis(db, sample_topic.id, "Neglected", created_days_ago=60, updated_days_ago=40)
    assert [t.statement for t in get_stale_theses(sample_topic.id, db)] == ["Neglected"]


def test_retired_thesis_never_stale(db, sample_topic):
    _insert_thesis(db, sample_topic.id, "Retired", created_days_ago=90)
    db.execute("UPDATE theses SET status = 'retired'")
    db.commit()
    assert get_stale_theses(sample_topic.id, db) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_theses.py -v`
Expected: new tests ERROR with `ImportError` (no `get_stale_theses`); Task 1 tests still pass.

- [ ] **Step 3: Implement** — replace the stub `src/perpetual_analyst/analyst/theses.py` entirely:

```python
"""Thesis lifecycle helpers: stale-flagging and report rendering. See SPEC §8.

Thesis CRUD (apply_thesis_update, get_active_theses) lives in analyst/memory.py,
the transactional write path owned by apply_all_memory_writes.
"""

from __future__ import annotations

import sqlite3

from perpetual_analyst.store.models import Thesis


def get_stale_theses(
    topic_id: int, conn: sqlite3.Connection, days: int = 30
) -> list[Thesis]:
    """Active theses untouched (no update; fallback: creation) for more than `days` days."""
    rows = conn.execute(
        """SELECT * FROM theses
           WHERE topic_id = ? AND status = 'active'
             AND datetime(COALESCE(updated_at, created_at)) <= datetime('now', ?)""",
        (topic_id, f"-{days} days"),
    ).fetchall()
    return [Thesis.from_row(row) for row in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_theses.py -v`
Expected: all pass.

- [ ] **Step 5: Commit** (cross the query half of TODO 6.3)

```powershell
git add src/perpetual_analyst/analyst/theses.py tests/test_theses.py TODO.md
git commit -m "feat: add get_stale_theses 30-day stale-flagging query"
```

---

### Task 3: `render_thesis_fragment` (TODO 6.4)

**Files:**
- Modify: `src/perpetual_analyst/analyst/theses.py`
- Test: `tests/test_theses.py` (append)

- [ ] **Step 1: Write the failing tests** (append)

```python
from perpetual_analyst.analyst.theses import render_thesis_fragment
from perpetual_analyst.store.models import Thesis as ThesisRow
from perpetual_analyst.store.models import ThesisUpdate as ThesisUpdateRow


def _thesis_row(statement="Open models reach parity"):
    return ThesisRow(
        id=1, topic_id=1, statement=statement, rationale=None,
        confidence=0.8, status="active", created_at="2026-06-01", updated_at=None,
    )


def _update_row(before, after, change="Third confirming signal this month."):
    return ThesisUpdateRow(
        id=1, thesis_id=1, change=change, confidence_before=before,
        confidence_after=after, triggered_by_item_id=None, created_at="2026-06-11",
    )


def test_render_empty_returns_empty_string():
    assert render_thesis_fragment([]) == ""


def test_render_shows_confidence_before_after():
    fragment = render_thesis_fragment([(_thesis_row(), _update_row(0.6, 0.8))])
    assert "### Thesis updates" in fragment
    assert "Open models reach parity" in fragment
    assert "0.60 → 0.80" in fragment
    assert "Third confirming signal" in fragment


def test_render_handles_missing_before_confidence():
    fragment = render_thesis_fragment([(_thesis_row(), _update_row(None, 0.5, "Created."))])
    assert "— → 0.50" in fragment
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_theses.py -v`
Expected: `ImportError: cannot import name 'render_thesis_fragment'`.

- [ ] **Step 3: Implement** — append to `theses.py` (and extend the models import):

```python
from perpetual_analyst.store.models import Thesis, ThesisUpdate
```

```python
def render_thesis_fragment(
    theses_with_updates: list[tuple[Thesis, ThesisUpdate]],
) -> str:
    """Markdown 'Thesis updates' fragment; empty string when nothing moved (SPEC §9)."""
    if not theses_with_updates:
        return ""
    lines = ["### Thesis updates", ""]
    for thesis, update in theses_with_updates:
        before = "—" if update.confidence_before is None else f"{update.confidence_before:.2f}"
        after = "—" if update.confidence_after is None else f"{update.confidence_after:.2f}"
        lines.append(
            f"- **{thesis.statement}** — confidence {before} → {after}. {update.change}"
        )
    return "\n".join(lines)
```

Note: `ThesisUpdate` here is the **DB row dataclass** from `store/models.py`, not the Pydantic `analyst/schemas.py` model of the same name. Do not import the schemas one in `theses.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_theses.py -v`
Expected: all pass.

- [ ] **Step 5: Commit** (cross TODO 6.4)

```powershell
git add src/perpetual_analyst/analyst/theses.py tests/test_theses.py TODO.md
git commit -m "feat: render thesis-updates report fragment with confidence before/after"
```

---

### Task 4: Stale-thesis block in `assemble_context` (TODO 6.3, wiring)

**Orchestrator: run `gitnexus_impact({target: "assemble_context", direction: "upstream"})` before dispatching this task.**

**Files:**
- Modify: `src/perpetual_analyst/analyst/agent.py:47-90`
- Test: `tests/test_agent.py` (append)

- [ ] **Step 1: Write the failing test** (append to `tests/test_agent.py`; reuse that file's existing imports/fixtures for `Settings` — if it builds `Settings` inline, follow its pattern):

```python
from perpetual_analyst.analyst.agent import assemble_context
from perpetual_analyst.config import ModelConfig, Settings


def _settings():
    return Settings(
        analyst=ModelConfig(id="test-analyst", thinking=False),
        triage=ModelConfig(id="test-triage", thinking=False),
    )


def test_assemble_context_flags_stale_theses(db, sample_topic):
    db.execute(
        "INSERT INTO theses (topic_id, statement, confidence, status, created_at, updated_at)"
        " VALUES (?, 'Dusty thesis', 0.5, 'active',"
        " datetime('now', '-45 days'), datetime('now', '-40 days'))",
        (sample_topic.id,),
    )
    db.commit()
    messages = assemble_context(sample_topic, [], db, "system prompt", _settings())
    user_content = messages[1]["content"]
    assert "## Stale theses — revisit or retire" in user_content
    assert "Dusty thesis" in user_content


def test_assemble_context_stale_section_present_when_empty(db, sample_topic):
    messages = assemble_context(sample_topic, [], db, "system prompt", _settings())
    user_content = messages[1]["content"]
    assert "## Stale theses — revisit or retire\n(none)" in user_content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_agent.py -v`
Expected: new tests FAIL (no stale section in prompt).

- [ ] **Step 3: Implement in `agent.py`**

Add to the memory imports block:

```python
from perpetual_analyst.analyst.theses import get_stale_theses
```

In `assemble_context`, after the `theses_text = (...)` assignment, add:

```python
    stale = get_stale_theses(topic.id, conn)
    stale_text = (
        "\n".join(
            f"[thesis:{t.id}] (last touched {t.updated_at or t.created_at}) {t.statement}"
            for t in stale
        )
        or "(none)"
    )
```

In `user_content`, after the `## Active theses` line, add:

```python
        f"## Stale theses — revisit or retire\n{stale_text}\n\n"
```

The section is always present (with `(none)`) so the prompt prefix stays stable for caching.

- [ ] **Step 4: Run the full suite**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests -v`
Expected: all pass.

- [ ] **Step 5: Commit** (cross remaining TODO 6.3; Task 6 fully crossed)

```powershell
git add src/perpetual_analyst/analyst/agent.py tests/test_agent.py TODO.md
git commit -m "feat: surface stale theses to the analyst in assembled context"
```

---

### Task 5: RSS fetcher (TODO 7.1)

**Files:**
- Create: `src/perpetual_analyst/ingestion/rss.py` (replace stub)
- Create: `tests/test_rss.py`

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import httpx
import pytest

from perpetual_analyst.ingestion import rss
from perpetual_analyst.store.models import Source

RSS_XML = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test Feed</title>
<item><title>First Post</title><link>https://example.com/1</link>
<pubDate>Mon, 08 Jun 2026 12:00:00 GMT</pubDate>
<description>Summary one</description></item>
<item><title>Second Post</title><link>https://example.com/2</link>
<pubDate>Wed, 10 Jun 2026 12:00:00 GMT</pubDate>
<description>Summary two</description></item>
</channel></rss>"""


@pytest.fixture
def rss_source(db):
    cur = db.execute(
        "INSERT INTO sources (type, url, name) VALUES"
        " ('rss', 'https://example.com/feed', 'Test Feed')"
    )
    db.commit()
    row = db.execute("SELECT * FROM sources WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Source.from_row(row)


class _FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        pass


@pytest.fixture
def feed_ok(monkeypatch):
    monkeypatch.setattr(rss.httpx, "get", lambda *a, **kw: _FakeResponse(RSS_XML))
    monkeypatch.setattr(rss.trafilatura, "fetch_url", lambda url: "<html>stub</html>")
    monkeypatch.setattr(rss.trafilatura, "extract", lambda html: f"Full text from {html}")


def test_fetch_inserts_new_items(db, rss_source, feed_ok):
    count = rss.fetch_rss(rss_source, db)
    assert count == 2
    rows = db.execute("SELECT title, raw_text, status FROM items ORDER BY id").fetchall()
    assert [r["title"] for r in rows] == ["First Post", "Second Post"]
    assert all("Full text" in r["raw_text"] for r in rows)
    src = db.execute("SELECT * FROM sources WHERE id = ?", (rss_source.id,)).fetchone()
    assert src["last_fetched_at"] is not None
    assert src["fetch_error_count"] == 0


def test_since_last_fetch_skips_old_entries(db, rss_source, feed_ok):
    db.execute(
        "UPDATE sources SET last_fetched_at = '2026-06-09 00:00:00' WHERE id = ?",
        (rss_source.id,),
    )
    db.commit()
    src = Source.from_row(
        db.execute("SELECT * FROM sources WHERE id = ?", (rss_source.id,)).fetchone()
    )
    count = rss.fetch_rss(src, db)
    assert count == 1
    titles = [r["title"] for r in db.execute("SELECT title FROM items").fetchall()]
    assert titles == ["Second Post"]


def test_refetch_dedupes_silently(db, rss_source, feed_ok):
    assert rss.fetch_rss(rss_source, db) == 2
    assert rss.fetch_rss(rss_source, db) == 0
    assert db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2


def test_extraction_failure_falls_back_to_summary(db, rss_source, monkeypatch):
    monkeypatch.setattr(rss.httpx, "get", lambda *a, **kw: _FakeResponse(RSS_XML))
    monkeypatch.setattr(rss.trafilatura, "fetch_url", lambda url: None)
    count = rss.fetch_rss(rss_source, db)
    assert count == 2
    texts = [r["raw_text"] for r in db.execute("SELECT raw_text FROM items").fetchall()]
    assert texts == ["Summary one", "Summary two"]


def test_feed_error_increments_count(db, rss_source, monkeypatch):
    def _boom(*a, **kw):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(rss.httpx, "get", _boom)
    assert rss.fetch_rss(rss_source, db) == 0
    src = db.execute("SELECT * FROM sources WHERE id = ?", (rss_source.id,)).fetchone()
    assert src["fetch_error_count"] == 1
    assert src["active"] == 1


def test_source_deactivated_after_five_errors(db, rss_source, monkeypatch):
    db.execute("UPDATE sources SET fetch_error_count = 4 WHERE id = ?", (rss_source.id,))
    db.commit()

    def _boom(*a, **kw):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(rss.httpx, "get", _boom)
    rss.fetch_rss(rss_source, db)
    src = db.execute("SELECT * FROM sources WHERE id = ?", (rss_source.id,)).fetchone()
    assert src["fetch_error_count"] == 5
    assert src["active"] == 0


def test_success_resets_error_count(db, rss_source, feed_ok):
    db.execute("UPDATE sources SET fetch_error_count = 3 WHERE id = ?", (rss_source.id,))
    db.commit()
    rss.fetch_rss(rss_source, db)
    src = db.execute("SELECT * FROM sources WHERE id = ?", (rss_source.id,)).fetchone()
    assert src["fetch_error_count"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_rss.py -v`
Expected: `AttributeError`/`ImportError` — stub has no `fetch_rss`, no `httpx`/`trafilatura` attributes.

- [ ] **Step 3: Implement** — replace `src/perpetual_analyst/ingestion/rss.py` entirely:

```python
"""RSS/Atom feed fetcher: httpx + feedparser + trafilatura. See SPEC §12 Phase 2."""

from __future__ import annotations

import hashlib
import sqlite3
import time

import feedparser
import httpx
import trafilatura

from perpetual_analyst.store.db import insert_item
from perpetual_analyst.store.models import Source

MAX_FETCH_ERRORS = 5
_TIMEOUT_SECONDS = 30.0


def _entry_timestamp(entry) -> str | None:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            return time.strftime("%Y-%m-%d %H:%M:%S", parsed)
    return None


def _extract_full_text(url: str | None) -> str | None:
    if not url:
        return None
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            return trafilatura.extract(downloaded)
    except Exception:
        return None
    return None


def _record_fetch_error(source_id: int, conn: sqlite3.Connection) -> None:
    conn.execute(
        "UPDATE sources SET fetch_error_count = fetch_error_count + 1 WHERE id = ?",
        (source_id,),
    )
    conn.execute(
        "UPDATE sources SET active = 0 WHERE id = ? AND fetch_error_count >= ?",
        (source_id, MAX_FETCH_ERRORS),
    )
    conn.commit()


def fetch_rss(source: Source, conn: sqlite3.Connection) -> int:
    """Fetch new entries for one RSS source. Returns the count of newly inserted items.

    Feed-level failures increment fetch_error_count (source deactivated at
    MAX_FETCH_ERRORS); item-level extraction failures fall back to the feed summary.
    """
    try:
        response = httpx.get(source.url, timeout=_TIMEOUT_SECONDS, follow_redirects=True)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        if feed.bozo and not feed.entries:
            raise ValueError(f"unparseable feed: {source.url}")
    except Exception:
        _record_fetch_error(source.id, conn)
        return 0

    inserted = 0
    for entry in feed.entries:
        published = _entry_timestamp(entry)
        if source.last_fetched_at and published and published <= source.last_fetched_at:
            continue
        link = getattr(entry, "link", None)
        text = _extract_full_text(link) or getattr(entry, "summary", None)
        if not text or not text.strip():
            continue
        is_new = insert_item(
            conn,
            source_id=source.id,
            content_hash=hashlib.sha256(text.strip().encode()).hexdigest(),
            title=getattr(entry, "title", None),
            url=link,
            author=getattr(entry, "author", None),
            published_at=published,
            raw_text=text,
        )
        if is_new:
            inserted += 1

    conn.execute(
        "UPDATE sources SET last_fetched_at = datetime('now'), fetch_error_count = 0"
        " WHERE id = ?",
        (source.id,),
    )
    conn.commit()
    return inserted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_rss.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit** (cross TODO 7.1)

```powershell
git add src/perpetual_analyst/ingestion/rss.py tests/test_rss.py TODO.md
git commit -m "feat: RSS fetcher with since-last-fetch, dedupe, and error-count deactivation"
```

---

### Task 6: Triage (TODO 7.2, 7.3)

**Files:**
- Create: `src/perpetual_analyst/analyst/triage.py` (replace stub)
- Create: `tests/test_triage.py`

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from perpetual_analyst.analyst.triage import CHUNK_SIZE, triage_items
from perpetual_analyst.config import ModelConfig, Settings
from perpetual_analyst.store.models import Item


@pytest.fixture
def settings():
    return Settings(
        analyst=ModelConfig(id="test-analyst", thinking=False),
        triage=ModelConfig(id="test-triage", thinking=False),
    )


def _client_returning(*payloads: str) -> MagicMock:
    client = MagicMock()
    responses = []
    for payload in payloads:
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = payload
        responses.append(response)
    client.chat.completions.create.side_effect = responses
    return client


def _items_in_db(db, sample_source, n):
    items = []
    for i in range(n):
        cur = db.execute(
            "INSERT INTO items (source_id, content_hash, title, raw_text)"
            " VALUES (?, ?, ?, ?)",
            (sample_source, f"hash_{i}", f"Item {i}", f"Text {i}"),
        )
        db.commit()
        row = db.execute("SELECT * FROM items WHERE id = ?", (cur.lastrowid,)).fetchone()
        items.append(Item.from_row(row))
    return items


def _payload(items, score):
    return json.dumps(
        [{"item_id": it.id, "score": score, "summary": f"Sum {it.id}"} for it in items]
    )


def test_scores_and_summaries_written(db, sample_source, settings):
    items = _items_in_db(db, sample_source, 2)
    client = _client_returning(_payload(items, 0.7))
    results = triage_items(items, "brief", client, settings, db)
    assert len(results) == 2
    rows = db.execute("SELECT triage_score, triage_summary, status FROM items").fetchall()
    assert all(r["triage_score"] == 0.7 for r in rows)
    assert all(r["status"] == "new" for r in rows)


def test_low_score_marked_skipped(db, sample_source, settings):
    items = _items_in_db(db, sample_source, 2)
    payload = json.dumps(
        [
            {"item_id": items[0].id, "score": 0.1, "summary": "meh"},
            {"item_id": items[1].id, "score": 0.2, "summary": "borderline"},
        ]
    )
    triage_items(items, "brief", _client_returning(payload), settings, db)
    statuses = {
        r["id"]: r["status"] for r in db.execute("SELECT id, status FROM items").fetchall()
    }
    assert statuses[items[0].id] == "skipped"
    assert statuses[items[1].id] == "new"


def test_code_fences_stripped(db, sample_source, settings):
    items = _items_in_db(db, sample_source, 1)
    payload = f"```json\n{_payload(items, 0.5)}\n```"
    results = triage_items(items, "brief", _client_returning(payload), settings, db)
    assert len(results) == 1


def test_parse_failure_retries_once_then_gives_up(db, sample_source, settings):
    items = _items_in_db(db, sample_source, 1)
    client = _client_returning("garbage", "more garbage")
    results = triage_items(items, "brief", client, settings, db)
    assert results == []
    assert client.chat.completions.create.call_count == 2
    row = db.execute("SELECT status, triage_score FROM items").fetchone()
    assert row["status"] == "new"
    assert row["triage_score"] is None


def test_retry_succeeds_second_time(db, sample_source, settings):
    items = _items_in_db(db, sample_source, 1)
    client = _client_returning("garbage", _payload(items, 0.9))
    results = triage_items(items, "brief", client, settings, db)
    assert len(results) == 1
    assert client.chat.completions.create.call_count == 2


def test_chunking_splits_calls(db, sample_source, settings):
    items = _items_in_db(db, sample_source, CHUNK_SIZE * 2 + 5)
    chunks = [items[i : i + CHUNK_SIZE] for i in range(0, len(items), CHUNK_SIZE)]
    client = _client_returning(*[_payload(chunk, 0.5) for chunk in chunks])
    results = triage_items(items, "brief", client, settings, db)
    assert len(results) == len(items)
    assert client.chat.completions.create.call_count == 3


def test_unknown_item_id_ignored(db, sample_source, settings):
    items = _items_in_db(db, sample_source, 1)
    payload = json.dumps(
        [
            {"item_id": items[0].id, "score": 0.6, "summary": "ok"},
            {"item_id": 99999, "score": 0.9, "summary": "hallucinated"},
        ]
    )
    results = triage_items(items, "brief", _client_returning(payload), settings, db)
    assert [r.item_id for r in results] == [items[0].id]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_triage.py -v`
Expected: `ImportError` (stub has no `triage_items`/`CHUNK_SIZE`).

- [ ] **Step 3: Implement** — replace `src/perpetual_analyst/analyst/triage.py` entirely:

```python
"""Relevance triage pass via the configured cheap model (settings.triage.id). See SPEC §4.

Protects the analyst's context window: the expensive model sees 10-30 distilled
items, not 200 raw articles. This is a function, not an agent (Invariant 1).
"""

from __future__ import annotations

import re
import sqlite3

import openai
from pydantic import BaseModel, Field, TypeAdapter

from perpetual_analyst.config import Settings
from perpetual_analyst.store.models import Item

CHUNK_SIZE = 20
SKIP_THRESHOLD = 0.2
_EXCERPT_CHARS = 1500

_PROMPT_TEMPLATE = """You are a relevance triage filter for an intelligence analyst.

Topic brief:
{brief}

Score each item below for relevance to the topic brief (0.0 = irrelevant,
1.0 = essential reading) and write a 2-line summary of each.

Items:
{items}

Return ONLY a JSON array, one object per item, no other text:
[{{"item_id": <int>, "score": <float 0-1>, "summary": "<2-line summary>"}}]"""


class TriageResult(BaseModel):
    item_id: int
    score: float = Field(ge=0.0, le=1.0)
    summary: str


_RESULTS = TypeAdapter(list[TriageResult])
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip())


def _format_items(items: list[Item]) -> str:
    blocks = []
    for item in items:
        excerpt = (item.raw_text or "")[:_EXCERPT_CHARS]
        blocks.append(f"item_id={item.id}\ntitle: {item.title or '(untitled)'}\n{excerpt}")
    return "\n\n".join(blocks)


def _triage_chunk(
    chunk: list[Item],
    topic_brief: str,
    client: openai.OpenAI,
    settings: Settings,
) -> list[TriageResult]:
    prompt = _PROMPT_TEMPLATE.format(brief=topic_brief, items=_format_items(chunk))
    for _ in range(2):
        response = client.chat.completions.create(
            model=settings.triage.id,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or ""
        try:
            return _RESULTS.validate_json(_strip_fences(text))
        except Exception as exc:
            prompt = (
                f"{prompt}\n\nYour previous reply failed validation ({exc}). "
                "Return ONLY the JSON array."
            )
    print(f"[triage] chunk of {len(chunk)} items failed validation twice; left untriaged")
    return []


def triage_items(
    items: list[Item],
    topic_brief: str,
    client: openai.OpenAI,
    settings: Settings,
    conn: sqlite3.Connection,
) -> list[TriageResult]:
    """Score + summarize items in chunks; writes triage columns and skip-status to DB."""
    known_ids = {item.id for item in items}
    accepted: list[TriageResult] = []
    for start in range(0, len(items), CHUNK_SIZE):
        chunk = items[start : start + CHUNK_SIZE]
        for result in _triage_chunk(chunk, topic_brief, client, settings):
            if result.item_id not in known_ids:
                continue
            conn.execute(
                "UPDATE items SET triage_score = ?, triage_summary = ?,"
                " status = CASE WHEN ? < ? THEN 'skipped' ELSE status END"
                " WHERE id = ?",
                (result.score, result.summary, result.score, SKIP_THRESHOLD, result.item_id),
            )
            accepted.append(result)
        conn.commit()
    return accepted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_triage.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit** (cross TODO 7.2 + 7.3)

```powershell
git add src/perpetual_analyst/analyst/triage.py tests/test_triage.py TODO.md
git commit -m "feat: batched triage pass with retry, skip threshold, and chunking"
```

---

### Task 7: FTS5 retrieval helpers (TODO 8.1, 8.2)

**Files:**
- Create: `src/perpetual_analyst/retrieval/search.py` (replace stub)
- Create: `tests/test_search.py`

**bm25 note:** SQLite FTS5 `bm25()` returns *negative* values where more-negative = better match. The recency boost therefore multiplies by **1.5** (making recent matches more negative → ranked higher), not 0.5.

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import pytest

from perpetual_analyst.retrieval.search import related_items, related_observations


def _obs(db, topic_id, content, days_ago=0, status="active"):
    db.execute(
        f"""INSERT INTO observations (topic_id, kind, content, importance, status, created_at)
            VALUES (?, 'fact', ?, 2, ?, datetime('now', '-{days_ago} days'))""",
        (topic_id, content, status),
    )
    db.commit()


def _item(db, source_id, title, text, days_ago=0, status="new"):
    cur = db.execute(
        f"""INSERT INTO items (source_id, content_hash, title, raw_text, status, fetched_at)
            VALUES (?, ?, ?, ?, ?, datetime('now', '-{days_ago} days'))""",
        (source_id, f"hash_{title}", title, text, status),
    )
    db.commit()
    return cur.lastrowid


@pytest.fixture
def linked_source(db, sample_topic, sample_source):
    db.execute(
        "INSERT INTO topic_sources (topic_id, source_id) VALUES (?, ?)",
        (sample_topic.id, sample_source),
    )
    db.commit()
    return sample_source


def test_related_observations_matches_keywords(db, sample_topic):
    _obs(db, sample_topic.id, "GPU export controls tightened in May")
    _obs(db, sample_topic.id, "New cafeteria menu announced")
    results = related_observations("export controls on GPUs", sample_topic.id, db)
    assert [o.content for o in results] == ["GPU export controls tightened in May"]


def test_related_observations_excludes_other_topics(db, sample_topic):
    db.execute(
        "INSERT INTO topics (user_id, slug, name) VALUES (1, 'other', 'Other')"
    )
    other_id = db.execute("SELECT id FROM topics WHERE slug = 'other'").fetchone()["id"]
    _obs(db, other_id, "GPU export controls tightened")
    assert related_observations("GPU export controls", sample_topic.id, db) == []


def test_related_observations_excludes_inactive(db, sample_topic):
    _obs(db, sample_topic.id, "GPU export controls tightened", status="expired")
    assert related_observations("GPU export controls", sample_topic.id, db) == []


def test_recent_observation_ranks_first(db, sample_topic):
    _obs(db, sample_topic.id, "Compute scaling continues unabated", days_ago=60)
    _obs(db, sample_topic.id, "Compute scaling shows new datapoint", days_ago=1)
    results = related_observations("compute scaling", sample_topic.id, db, k=2)
    assert len(results) == 2
    assert "new datapoint" in results[0].content


def test_related_observations_k_limit(db, sample_topic):
    for i in range(8):
        _obs(db, sample_topic.id, f"Compute trend number {i}")
    assert len(related_observations("compute trend", sample_topic.id, db, k=5)) == 5


def test_hostile_query_text_does_not_raise(db, sample_topic):
    _obs(db, sample_topic.id, "Anything at all")
    related_observations('AND "NEAR( OR *', sample_topic.id, db)
    related_observations("", sample_topic.id, db)


def test_related_items_joins_topic_and_excludes(db, sample_topic, linked_source):
    matching = _item(db, linked_source, "GPU Export Rules", "Export controls on GPUs expand")
    _item(db, linked_source, "Cooking Tips", "How to roast vegetables")
    skipped = _item(
        db, linked_source, "GPU Export Skipped", "Export controls skipped", status="skipped"
    )
    results = related_items("GPU export controls", sample_topic.id, db)
    ids = [i.id for i in results]
    assert matching in ids
    assert skipped not in ids


def test_related_items_excludes_current_batch(db, sample_topic, linked_source):
    current = _item(db, linked_source, "GPU Export Today", "Export controls on GPUs today")
    prior = _item(db, linked_source, "GPU Export Last Week", "Export controls on GPUs before")
    results = related_items(
        "GPU export controls", sample_topic.id, db, exclude_ids=[current]
    )
    ids = [i.id for i in results]
    assert prior in ids
    assert current not in ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_search.py -v`
Expected: `ImportError` (stub has no functions).

- [ ] **Step 3: Implement** — replace `src/perpetual_analyst/retrieval/search.py` entirely:

```python
"""FTS5 keyword search for the analyst's related-context retrieval. See SPEC §6.

V1 is keyword search only — no vectors. bm25() scores are negative
(more negative = better), so the recency boost multiplies by >1.
"""

from __future__ import annotations

import re
import sqlite3

from perpetual_analyst.store.models import Item, Observation

_MAX_TERMS = 30
_RECENT_BOOST = 1.5


def _fts_query(text: str) -> str:
    """Quote each word so arbitrary text can't inject FTS5 query syntax."""
    terms = re.findall(r"\w+", text)
    return " OR ".join(f'"{term}"' for term in terms[:_MAX_TERMS])


def related_observations(
    text: str, topic_id: int, conn: sqlite3.Connection, k: int = 5
) -> list[Observation]:
    query = _fts_query(text)
    if not query:
        return []
    rows = conn.execute(
        """SELECT o.* FROM observations_fts f
           JOIN observations o ON o.id = f.rowid
           WHERE f MATCH ? AND o.topic_id = ? AND o.status = 'active'
           ORDER BY bm25(f)
                    * CASE WHEN o.created_at >= datetime('now', '-30 days')
                           THEN ? ELSE 1.0 END
           LIMIT ?""",
        (query, topic_id, _RECENT_BOOST, k),
    ).fetchall()
    return [Observation.from_row(row) for row in rows]


def related_items(
    text: str,
    topic_id: int,
    conn: sqlite3.Connection,
    k: int = 3,
    exclude_ids: list[int] | None = None,
) -> list[Item]:
    query = _fts_query(text)
    if not query:
        return []
    exclude = exclude_ids or []
    placeholders = ",".join("?" for _ in exclude) or "NULL"
    rows = conn.execute(
        f"""SELECT i.* FROM items_fts f
            JOIN items i ON i.id = f.rowid
            JOIN topic_sources ts ON ts.source_id = i.source_id AND ts.topic_id = ?
            WHERE f MATCH ? AND i.status != 'skipped'
              AND i.id NOT IN ({placeholders})
            ORDER BY bm25(f)
                     * CASE WHEN i.fetched_at >= datetime('now', '-14 days')
                            THEN ? ELSE 1.0 END
            LIMIT ?""",
        (topic_id, query, *exclude, _RECENT_BOOST, k),
    ).fetchall()
    return [Item.from_row(row) for row in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_search.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit** (cross TODO 8.1 + 8.2)

```powershell
git add src/perpetual_analyst/retrieval/search.py tests/test_search.py TODO.md
git commit -m "feat: FTS5 related-context retrieval with recency boost and query sanitization"
```

---

### Task 8: Wire related prior context into `assemble_context` (TODO 8.3)

**Orchestrator: run `gitnexus_impact({target: "assemble_context", direction: "upstream"})` before dispatching (again — it changed in Task 4).**

**Files:**
- Modify: `src/perpetual_analyst/analyst/agent.py`
- Test: `tests/test_agent.py` (append)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_agent.py`; reuse `_settings()` from Task 4 and the `sample_source` fixture):

```python
def test_assemble_context_attaches_related_prior_context(db, sample_topic, sample_source):
    db.execute(
        "INSERT INTO topic_sources (topic_id, source_id) VALUES (?, ?)",
        (sample_topic.id, sample_source),
    )
    db.execute(
        "INSERT INTO observations (topic_id, kind, content, importance, status)"
        " VALUES (?, 'signal', 'GPU export controls tightened in May', 2, 'active')",
        (sample_topic.id,),
    )
    cur = db.execute(
        "INSERT INTO items (source_id, content_hash, title, raw_text, triage_summary)"
        " VALUES (?, 'hash_new', 'Export controls on GPUs expanded',"
        " 'Today the export controls were expanded.', 'GPU export controls expanded again')",
        (sample_source,),
    )
    db.commit()
    row = db.execute("SELECT * FROM items WHERE id = ?", (cur.lastrowid,)).fetchone()
    new_item = Item.from_row(row)

    messages = assemble_context(sample_topic, [new_item], db, "system prompt", _settings())
    user_content = messages[1]["content"]
    assert "Related prior context:" in user_content
    assert "[obs:" in user_content
    assert "GPU export controls tightened in May" in user_content


def test_assemble_context_no_related_context_when_nothing_matches(db, sample_topic, sample_items):
    messages = assemble_context(sample_topic, sample_items, db, "system prompt", _settings())
    assert "Related prior context:" not in messages[1]["content"]
```

(`Item` is imported in `test_agent.py`'s existing imports via conftest models — if not, add `from perpetual_analyst.store.models import Item`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_agent.py -v`
Expected: first new test FAILS (no "Related prior context" in prompt).

- [ ] **Step 3: Implement in `agent.py`**

Add import:

```python
from perpetual_analyst.retrieval.search import related_items, related_observations
```

Add a module-level constant next to `_ITEM_TEXT_LIMIT`:

```python
_RELATED_OBS_CHARS = 200  # one-line truncation for related-context entries
```

Add this helper above `assemble_context`:

```python
def _render_item_block(
    item: Item, topic_id: int, conn: sqlite3.Connection, exclude_ids: list[int]
) -> str:
    parts = [f"[item:{item.id}] {item.title or '(untitled)'}"]
    if item.triage_summary:
        parts.append(f"Triage summary: {item.triage_summary}")
    parts.append((item.raw_text or "(no text)")[:_ITEM_TEXT_LIMIT])

    query_text = f"{item.title or ''} {item.triage_summary or ''}".strip()
    if query_text:
        context_lines = [
            f"  [obs:{o.id}] {o.content[:_RELATED_OBS_CHARS]}"
            for o in related_observations(query_text, topic_id, conn)
        ]
        context_lines += [
            f"  [item:{r.id}] {r.title or '(untitled)'}"
            for r in related_items(query_text, topic_id, conn, exclude_ids=exclude_ids)
        ]
        if context_lines:
            parts.append("Related prior context:\n" + "\n".join(context_lines))
    return "\n".join(parts)
```

Replace the `items_text = (...)` expression inside `assemble_context` with:

```python
    exclude_ids = [item.id for item in items]
    items_text = (
        "\n\n".join(_render_item_block(item, topic.id, conn, exclude_ids) for item in items)
        or "(no new items today)"
    )
```

- [ ] **Step 4: Run the full suite**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests -v`
Expected: all pass.

- [ ] **Step 5: Commit** (cross TODO 8.3; Task 8 fully crossed)

```powershell
git add src/perpetual_analyst/analyst/agent.py tests/test_agent.py TODO.md
git commit -m "feat: attach related prior context per item in analyst prompt"
```

---

### Task 8b: Mark items `analyzed` after the analyst run (TODO 7.3, second half)

**Orchestrator: run `gitnexus_impact({target: "run_topic", direction: "upstream"})` before dispatching.**

**Files:**
- Modify: `src/perpetual_analyst/analyst/agent.py` (`run_topic`)
- Test: `tests/test_agent.py` (append)

- [ ] **Step 1: Write the failing test** (append to `tests/test_agent.py`; uses the existing `mock_openrouter` conftest fixture):

```python
from perpetual_analyst.analyst.agent import run_topic


def test_run_topic_marks_items_analyzed(db, sample_topic, sample_items, mock_openrouter):
    result = run_topic(sample_topic, sample_items, db, mock_openrouter, _settings())
    assert result is not None
    statuses = [
        r["status"]
        for r in db.execute(
            "SELECT status FROM items WHERE id IN (?, ?, ?)",
            [i.id for i in sample_items],
        ).fetchall()
    ]
    assert statuses == ["analyzed", "analyzed", "analyzed"]


def test_dry_run_does_not_mark_items(db, sample_topic, sample_items, mock_openrouter):
    run_topic(sample_topic, sample_items, db, mock_openrouter, _settings(), dry_run=True)
    statuses = [r["status"] for r in db.execute("SELECT status FROM items").fetchall()]
    assert all(s == "new" for s in statuses)
```

(If `test_agent.py` already imports `run_topic`, skip the duplicate import.)

- [ ] **Step 2: Run tests to verify the first fails**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_agent.py -v`
Expected: `test_run_topic_marks_items_analyzed` FAILS (statuses stay `new`).

- [ ] **Step 3: Implement** — in `run_topic`, after the `apply_all_memory_writes(topic.id, result, conn)` line, add:

```python
    if items:
        placeholders = ",".join("?" for _ in items)
        conn.execute(
            f"UPDATE items SET status = 'analyzed' WHERE id IN ({placeholders})",
            [item.id for item in items],
        )
        conn.commit()
```

- [ ] **Step 4: Run the full suite**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests -v`
Expected: all pass.

- [ ] **Step 5: Commit** (cross remaining TODO 7.3)

```powershell
git add src/perpetual_analyst/analyst/agent.py tests/test_agent.py TODO.md
git commit -m "feat: mark items analyzed after successful analyst run"
```

---

### Task 9: Config loaders + `sync_config` (TODO 8.5.1)

**Files:**
- Modify: `src/perpetual_analyst/config.py`
- Create: `tests/test_config.py`

**Note:** `sources` has no UNIQUE constraint on `url`, so the upsert is SELECT-then-INSERT/UPDATE, not `ON CONFLICT`. Inbox-type sources may exist in the DB without YAML entries (they're created implicitly), so deactivation of YAML-absent sources exempts `type = 'inbox'`.

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import pytest

from perpetual_analyst.config import SourceConfig, TopicConfig, sync_config


def _topic(slug="ai-labs", name="AI Labs", brief="Track the labs"):
    return TopicConfig(slug=slug, name=name, brief=brief)


def _source(name="Feed A", url="https://a.example/feed", topics=("ai-labs",)):
    return SourceConfig(name=name, type="rss", url=url, topics=list(topics))


def test_sync_inserts_topic_and_source_with_link(db):
    sync_config(db, [_topic()], [_source()])
    topic = db.execute("SELECT * FROM topics WHERE slug = 'ai-labs'").fetchone()
    assert topic["name"] == "AI Labs"
    source = db.execute("SELECT * FROM sources WHERE url = 'https://a.example/feed'").fetchone()
    assert source["type"] == "rss"
    link = db.execute(
        "SELECT * FROM topic_sources WHERE topic_id = ? AND source_id = ?",
        (topic["id"], source["id"]),
    ).fetchone()
    assert link is not None


def test_sync_is_idempotent(db):
    sync_config(db, [_topic()], [_source()])
    sync_config(db, [_topic()], [_source()])
    assert db.execute("SELECT COUNT(*) FROM topics WHERE slug='ai-labs'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM topic_sources").fetchone()[0] == 1


def test_sync_updates_definition_columns(db):
    sync_config(db, [_topic()], [_source()])
    sync_config(db, [_topic(name="AI Frontier Labs", brief="New brief")], [_source()])
    topic = db.execute("SELECT * FROM topics WHERE slug = 'ai-labs'").fetchone()
    assert topic["name"] == "AI Frontier Labs"
    assert topic["brief"] == "New brief"


def test_sync_preserves_runtime_columns(db):
    sync_config(db, [_topic()], [_source()])
    db.execute(
        "UPDATE sources SET last_fetched_at = '2026-06-01 00:00:00', fetch_error_count = 3"
    )
    db.commit()
    sync_config(db, [_topic()], [_source()])
    source = db.execute("SELECT * FROM sources").fetchone()
    assert source["last_fetched_at"] == "2026-06-01 00:00:00"
    assert source["fetch_error_count"] == 3


def test_sync_deactivates_removed_rows(db):
    sync_config(db, [_topic(), _topic(slug="old", name="Old")], [_source()])
    sync_config(db, [_topic()], [])
    old = db.execute("SELECT active FROM topics WHERE slug = 'old'").fetchone()
    assert old["active"] == 0
    source = db.execute("SELECT active FROM sources").fetchone()
    assert source["active"] == 0


def test_sync_leaves_inbox_sources_alone(db, sample_source):
    # sample_source fixture is type='inbox' with no YAML entry
    sync_config(db, [_topic()], [_source()])
    inbox = db.execute("SELECT active FROM sources WHERE id = ?", (sample_source,)).fetchone()
    assert inbox["active"] == 1


def test_sync_unknown_topic_slug_raises(db):
    with pytest.raises(ValueError, match="unknown topic"):
        sync_config(db, [], [_source(topics=("nope",))])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_config.py -v`
Expected: `ImportError` (no `TopicConfig`/`SourceConfig`/`sync_config`).

- [ ] **Step 3: Implement** — append to `src/perpetual_analyst/config.py` (extend existing imports with `sqlite3` and `field`):

```python
import sqlite3
from dataclasses import dataclass, field
```

```python
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
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return [TopicConfig(**entry) for entry in data.get("topics") or []]


def load_sources(path: str = "config/sources.yaml") -> list[SourceConfig]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
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
    """
    for tc in topics:
        conn.execute(
            """INSERT INTO topics (slug, name, brief, active) VALUES (?, ?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET
                 name = excluded.name, brief = excluded.brief, active = excluded.active""",
            (tc.slug, tc.name, tc.brief, int(tc.active)),
        )
    slugs = [tc.slug for tc in topics]
    slug_placeholders = ",".join("?" for _ in slugs) or "NULL"
    conn.execute(
        f"UPDATE topics SET active = 0 WHERE slug NOT IN ({slug_placeholders})", slugs
    )

    synced_ids: list[int] = []
    for sc in sources:
        key_column = "url" if sc.url else "name"
        key_value = sc.url or sc.name
        row = conn.execute(
            f"SELECT id FROM sources WHERE {key_column} = ?", (key_value,)
        ).fetchone()
        if row:
            source_id = row["id"]
            conn.execute(
                "UPDATE sources SET name = ?, type = ?, url = ?, active = ? WHERE id = ?",
                (sc.name, sc.type, sc.url, int(sc.active), source_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO sources (name, type, url, active) VALUES (?, ?, ?, ?)",
                (sc.name, sc.type, sc.url, int(sc.active)),
            )
            source_id = cur.lastrowid
        synced_ids.append(source_id)

        conn.execute("DELETE FROM topic_sources WHERE source_id = ?", (source_id,))
        for slug in sc.topics:
            topic_row = conn.execute(
                "SELECT id FROM topics WHERE slug = ?", (slug,)
            ).fetchone()
            if topic_row is None:
                raise ValueError(f"source {sc.name!r} references unknown topic {slug!r}")
            conn.execute(
                "INSERT OR IGNORE INTO topic_sources (topic_id, source_id) VALUES (?, ?)",
                (topic_row["id"], source_id),
            )

    id_placeholders = ",".join("?" for _ in synced_ids) or "NULL"
    conn.execute(
        f"UPDATE sources SET active = 0"
        f" WHERE type != 'inbox' AND id NOT IN ({id_placeholders})",
        synced_ids,
    )
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_config.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit** (cross TODO 8.5.1)

```powershell
git add src/perpetual_analyst/config.py tests/test_config.py TODO.md
git commit -m "feat: YAML config loaders and idempotent sync_config upsert"
```

---

### Task 10: CLI `topic add` / `source add` (TODO 8.5.2)

**Files:**
- Modify: `src/perpetual_analyst/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

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


def test_topic_add_appends_yaml_and_syncs(tmp_path, monkeypatch):
    topics_path, _ = _write_configs(tmp_path, monkeypatch)
    db_path = str(tmp_path / "test.db")
    result = runner.invoke(
        cli.app,
        ["topic", "add", "ai-labs", "--name", "AI Labs", "--brief", "Track the labs",
         "--db-path", db_path],
    )
    assert result.exit_code == 0, result.output
    data = yaml.safe_load(topics_path.read_text(encoding="utf-8"))
    assert data["topics"][0]["slug"] == "ai-labs"

    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM topics WHERE slug = 'ai-labs'").fetchone()
    conn.close()
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
    runner.invoke(
        cli.app, ["topic", "add", "ai-labs", "--name", "AI Labs", "--db-path", db_path]
    )
    result = runner.invoke(
        cli.app,
        ["source", "add", "--topic", "ai-labs", "--type", "rss",
         "--url", "https://a.example/feed", "--name", "Feed A", "--db-path", db_path],
    )
    assert result.exit_code == 0, result.output
    data = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    assert data["sources"][0]["url"] == "https://a.example/feed"

    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    link = conn.execute(
        "SELECT COUNT(*) FROM topic_sources ts"
        " JOIN topics t ON t.id = ts.topic_id WHERE t.slug = 'ai-labs'"
    ).fetchone()[0]
    conn.close()
    assert link == 1


def test_source_add_unknown_topic_fails(tmp_path, monkeypatch):
    _write_configs(tmp_path, monkeypatch)
    db_path = str(tmp_path / "test.db")
    result = runner.invoke(
        cli.app,
        ["source", "add", "--topic", "nope", "--type", "rss",
         "--url", "https://a.example/feed", "--name", "Feed A", "--db-path", db_path],
    )
    assert result.exit_code == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_cli.py -v`
Expected: FAIL — `cli` has no `TOPICS_PATH` and no `topic add` command.

- [ ] **Step 3: Implement** — replace `src/perpetual_analyst/cli.py` entirely:

```python
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


@topic_app.command("add")
def topic_add(
    slug: str,
    name: str = typer.Option(..., help="Display name"),
    brief: str = typer.Option(None, help="What you care about — seeds the dossier"),
    db_path: str = typer.Option("data/analyst.db", help="SQLite DB path"),
) -> None:
    """Add a topic to config/topics.yaml and sync to the DB."""
    path = Path(TOPICS_PATH)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    topics = data.get("topics") or []
    if any(entry["slug"] == slug for entry in topics):
        typer.echo(f"topic {slug!r} already exists")
        raise typer.Exit(1)
    topics.append({"slug": slug, "name": name, "brief": brief, "active": True})
    data["topics"] = topics
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
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
    path = Path(SOURCES_PATH)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources = data.get("sources") or []
    for entry in sources:
        if (url and entry.get("url") == url) or (not url and entry.get("name") == name):
            if topic not in (entry.get("topics") or []):
                entry.setdefault("topics", []).append(topic)
            break
    else:
        sources.append(
            {"name": name, "type": type, "url": url, "active": True, "topics": [topic]}
        )
    data["sources"] = sources
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
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
```

**Caveat for `source add`:** if the sync fails with unknown topic, the YAML was already written. Acceptable for v1 — re-running `topic add` then any sync repairs it. Do not add rollback logic.

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_cli.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit** (cross TODO 8.5.2)

```powershell
git add src/perpetual_analyst/cli.py tests/test_cli.py TODO.md
git commit -m "feat: analyst topic add / source add CLI with YAML append and sync"
```

---

### Task 11: Real config + smoke marker plumbing (TODO 8.5.3)

**Files:**
- Modify: `config/topics.yaml`
- Modify: `config/sources.yaml`
- Modify: `pyproject.toml`

- [ ] **Step 1: Verify candidate third feed is reachable**

Run:
```powershell
C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -c "import httpx; [print(u, httpx.get(u, timeout=15, follow_redirects=True).status_code) for u in ['https://rss.arxiv.org/rss/cs.AI', 'https://simonwillison.net/atom/everything/', 'https://openai.com/news/rss.xml', 'https://deepmind.google/blog/rss.xml']]"
```
Expected: first two return 200. Pick the first of the remaining candidates that returns 200 as the third feed; if none do, proceed with just the two.

- [ ] **Step 2: Write the real config** — replace `config/topics.yaml`:

```yaml
# config/topics.yaml
# Managed via `analyst topic add` or edited directly.

topics:
  - slug: ai-frontier-labs
    name: "AI frontier labs"
    brief: "Track model releases, safety policy, compute trends, and competitive dynamics among frontier AI labs."
    active: true
```

Replace `config/sources.yaml` (swap/drop the third entry per Step 1's result):

```yaml
# config/sources.yaml
# Managed via `analyst source add` or edited directly.

sources:
  - name: "arXiv cs.AI"
    type: rss
    url: "https://rss.arxiv.org/rss/cs.AI"
    active: true
    topics:
      - ai-frontier-labs
  - name: "Simon Willison"
    type: rss
    url: "https://simonwillison.net/atom/everything/"
    active: true
    topics:
      - ai-frontier-labs
  - name: "OpenAI News"
    type: rss
    url: "https://openai.com/news/rss.xml"
    active: true
    topics:
      - ai-frontier-labs
```

- [ ] **Step 3: Add the smoke marker to `pyproject.toml`** — replace the `[tool.pytest.ini_options]` section:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-m 'not smoke'"
markers = [
    "smoke: live network + API end-to-end test; run explicitly with `pytest -m smoke`",
]
```

- [ ] **Step 4: Verify the default suite still runs and collects no smoke tests**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests -v`
Expected: all pass (smoke marker registered, nothing deselected yet).

- [ ] **Step 5: Commit** (cross TODO 8.5.3)

```powershell
git add config/topics.yaml config/sources.yaml pyproject.toml
git commit -m "feat: real AI-frontier-labs topic/source config and smoke test marker"
```

(Also stage TODO.md with the crossed sub-item.)

---

### Task 12: Live smoke test (TODO 8.5.4)

**Files:**
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Write the smoke test**

```python
"""Live end-to-end smoke test: real feeds, real triage, one real analyst run.

Run explicitly: pytest -m smoke
Requires OPENROUTER_API_KEY in .env and network access. Costs ~cents
(triage on deepseek-flash) plus one analyst call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from perpetual_analyst.analyst.agent import make_client, run_topic
from perpetual_analyst.analyst.triage import SKIP_THRESHOLD, triage_items
from perpetual_analyst.config import load_settings, load_sources, load_topics, sync_config
from perpetual_analyst.ingestion.rss import fetch_rss
from perpetual_analyst.store.db import init_db
from perpetual_analyst.store.models import Item, Source, Topic

SMOKE_DB = "data/smoke-phase2.db"
MAX_ANALYST_ITEMS = 10


@pytest.mark.smoke
def test_full_pipeline_live():
    Path(SMOKE_DB).unlink(missing_ok=True)
    conn = init_db(SMOKE_DB)
    sync_config(conn, load_topics(), load_sources())

    topic_row = conn.execute("SELECT * FROM topics WHERE active = 1 LIMIT 1").fetchone()
    assert topic_row, "no active topic in config/topics.yaml"
    topic = Topic.from_row(topic_row)

    sources = [
        Source.from_row(r)
        for r in conn.execute(
            "SELECT s.* FROM sources s JOIN topic_sources ts ON ts.source_id = s.id"
            " WHERE ts.topic_id = ? AND s.type = 'rss' AND s.active = 1",
            (topic.id,),
        ).fetchall()
    ]
    assert sources, "no active rss sources linked to topic"

    total = sum(fetch_rss(source, conn) for source in sources)
    assert total > 0, "no items fetched from live feeds"

    items = [
        Item.from_row(r)
        for r in conn.execute("SELECT * FROM items WHERE status = 'new'").fetchall()
    ]
    settings = load_settings()
    client = make_client()
    results = triage_items(items, topic.brief or "", client, settings, conn)
    assert results, "triage returned no validated results"

    keep = [
        Item.from_row(r)
        for r in conn.execute(
            "SELECT * FROM items WHERE status = 'new' AND triage_score >= ?"
            " ORDER BY triage_score DESC LIMIT ?",
            (SKIP_THRESHOLD, MAX_ANALYST_ITEMS),
        ).fetchall()
    ]
    assert keep, "triage skipped everything — check the topic brief or feeds"

    analysis = run_topic(topic, keep, conn, client, settings)
    assert analysis is not None
    assert analysis.report_section_markdown or analysis.nothing_significant
    if analysis.new_observations:
        obs_count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        assert obs_count == len(analysis.new_observations)
    conn.close()
```

- [ ] **Step 2: Verify it is deselected by default**

Run: `$env:PYTHONPATH = "$PWD\src"; C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests -v`
Expected: all pass; output shows `1 deselected`.

- [ ] **Step 3: Commit the test (without running it live yet)**

```powershell
git add tests/test_smoke.py TODO.md
git commit -m "test: live end-to-end smoke test behind -m smoke marker"
```

- [ ] **Step 4: Run the smoke test live (orchestrator decision point — costs real money, hits real feeds)**

`.env` is gitignored, so the worktree doesn't have it. Copy it from the main repo first, then run:
```powershell
Copy-Item C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.env .env
$env:PYTHONPATH = "$PWD\src"
C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests/test_smoke.py -m smoke -v
```
Expected: 1 passed (typically 1–3 minutes: feed fetches + per-article trafilatura + 2 LLM calls). On feed flakiness, rerun once; on triage validation failure, inspect the printed `[triage]` line before changing code. Cross TODO 8.5.4 and amend nothing — record the run result in the PR description instead.

---

## Spec deviations locked during planning

1. **bm25 recency boost is ×1.5, not ×0.5** — FTS5 bm25 scores are negative; multiplying by 0.5 would *penalize* recent matches. The spec's "0.5" wording is corrected by this plan (update the spec file in the same commit as Task 7 if desired, or leave with this note).
2. **Inbox-type sources are exempt from sync deactivation** — they exist in the DB without YAML entries by design.

## TODO sub-item → task map

| TODO | Plan task |
|---|---|
| 6.1 apply ThesisUpdates | Task 1 (regression tests; code pre-exists in memory.py) |
| 6.2 ≤7 enforcement | Task 1 (regression test) |
| 6.3 stale-flagging | Task 2 (query) + Task 4 (context wiring) |
| 6.4 thesis fragment | Task 3 |
| 7.1 rss.py | Task 5 |
| 7.2 triage batch call | Task 6 |
| 7.3 skipped/analyzed status | Task 6 (skipped) + Task 8b (analyzed in run_topic) |
| 8.1 search helpers | Task 7 |
| 8.2 recency weighting | Task 7 |
| 8.3 context wiring | Task 8 |
| 8.5.1 config sync | Task 9 |
| 8.5.2 CLI | Task 10 |
| 8.5.3 real YAML | Task 11 |
| 8.5.4 smoke test | Task 12 |
