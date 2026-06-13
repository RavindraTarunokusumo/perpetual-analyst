# Phase 3 — Automated Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement TODO Tasks 9–10 — report assembly + rendering, Telegram delivery, the `daily_run` orchestrator, scheduler docs — plus the Phase 2 handoff items, per `docs/superpowers/specs/2026-06-12-phase-3-automated-delivery-design.md`.

**Architecture:** Pure-function pipeline: `daily_run.run_daily` orchestrates sync → ingest → triage → analyze → assemble → persist → deliver with per-stage/per-topic try/except. One daily structured digest LLM call (`DigestOutput`). Telegram is env-gated and retried via `delivered_at IS NULL`.

**Tech Stack:** Python 3.12, sqlite3, openai SDK on OpenRouter, python-telegram-bot (async, send-only), typer, pytest (all mocked — no live API/Telegram this phase).

---

## Environment notes (read first)

- **Worktree:** `C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.worktree\phase-3` (branch `phase-3-automated-delivery`). All paths relative to it.
- **Tests need PYTHONPATH** (package not pip-installed). From worktree root:
  ```powershell
  $env:PYTHONPATH = "C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.worktree\phase-3\src"
  C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m pytest tests -q
  ```
  Baseline: 101 passed, 1 deselected.
- **Pre-commit before every commit** (restage your files if hooks reformat):
  ```powershell
  C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\pre-commit run --all-files
  ```
- One plan task = one commit; stage specific files only; git note per commit (`.github/git_notes_template.md`); cross TODO.md sub-items in the same commit. PowerShell here-strings `@'...'@` close `'@` at column 0. Do NOT run `npx gitnexus analyze` inside the worktree (it rewrites AGENTS/CLAUDE.md — Phase 2 insight).
- **Orchestrator:** run `gitnexus_impact` before Task 4 (`sync_config`) and Task 6 (`cli.py run`); both expected LOW.
- Conftest fixtures available: `db`, `sample_topic`, `sample_source` (inbox-type), `sample_items`, `settings`, `mock_openrouter` (returns a canned `TopicAnalysis` at `choices[0].message.parsed`).

---

### Task 1: `render_citations` (TODO 9.2)

**Files:**
- Create: `src/perpetual_analyst/report/render.py` (replace stub)
- Create: `tests/test_render.py`

- [ ] **Step 1: failing tests** — create `tests/test_render.py`:

```python
from __future__ import annotations

from perpetual_analyst.report.render import render_citations


def _item(db, source_id, title, url):
    cur = db.execute(
        "INSERT INTO items (source_id, content_hash, title, url) VALUES (?, ?, ?, ?)",
        (source_id, f"hash_{title}", title, url),
    )
    db.commit()
    return cur.lastrowid


def test_tags_become_numbered_footnotes(db, sample_source):
    a = _item(db, sample_source, "Alpha Post", "https://example.com/a")
    b = _item(db, sample_source, "Beta Post", "https://example.com/b")
    text = f"First [item:{a}] then [item:{b}] then [item:{a}] again."
    rendered = render_citations(text, db)
    assert "[^1]" in rendered and "[^2]" in rendered
    assert rendered.count("[^1]") == 2  # repeated citation reuses its number
    assert "## Sources reviewed" in rendered
    assert "[^1]: Alpha Post — https://example.com/a" in rendered
    assert "[^2]: Beta Post — https://example.com/b" in rendered


def test_unknown_item_id_renders_plain(db):
    rendered = render_citations("See [item:999].", db)
    assert "item:999" in rendered
    assert "[^" not in rendered
    assert "## Sources reviewed" not in rendered


def test_obs_and_thesis_tags_untouched(db, sample_source):
    a = _item(db, sample_source, "Alpha", None)
    rendered = render_citations(f"[obs:3] and [thesis:4] and [item:{a}]", db)
    assert "[obs:3]" in rendered and "[thesis:4]" in rendered
    assert "(no url)" in rendered


def test_no_tags_passthrough(db):
    assert render_citations("Plain text.", db) == "Plain text."
```

- [ ] **Step 2: run, expect ImportError** — `...python -m pytest tests/test_render.py -v`

- [ ] **Step 3: implement** — replace `src/perpetual_analyst/report/render.py`:

```python
"""Citation rendering: [item:N] -> numbered footnote links. See SPEC §6/§9."""

from __future__ import annotations

import re
import sqlite3

_ITEM_TAG_RE = re.compile(r"\[item:(\d+)\]")


def render_citations(markdown: str, conn: sqlite3.Connection) -> str:
    """Replace [item:N] with [^k] footnotes; unknown ids render as plain text.

    [obs:N]/[thesis:N] tags are internal memory references and pass through.
    """
    numbering: dict[int, int] = {}
    rows: dict[int, sqlite3.Row] = {}

    def _replace(match: re.Match[str]) -> str:
        item_id = int(match.group(1))
        if item_id not in rows:
            row = conn.execute(
                "SELECT title, url FROM items WHERE id = ?", (item_id,)
            ).fetchone()
            if row is None:
                return f"item:{item_id}"
            rows[item_id] = row
            numbering[item_id] = len(numbering) + 1
        return f"[^{numbering[item_id]}]"

    body = _ITEM_TAG_RE.sub(_replace, markdown)
    if not numbering:
        return body

    lines = ["", "## Sources reviewed", ""]
    for item_id, k in sorted(numbering.items(), key=lambda pair: pair[1]):
        row = rows[item_id]
        title = row["title"] or "(untitled)"
        url = row["url"] or "(no url)"
        lines.append(f"[^{k}]: {title} — {url}")
    return body + "\n".join(lines) + "\n"
```

- [ ] **Step 4: run, 4 passed; full suite green**
- [ ] **Step 5: commit** (cross TODO 9 sub-item 2)

```powershell
git add src/perpetual_analyst/report/render.py tests/test_render.py TODO.md
git commit -m "feat: render [item:N] citations as numbered footnotes"
```

---

### Task 2: `DigestOutput` schema + digest prompt (TODO 9 sub-item 3)

**Files:**
- Modify: `src/perpetual_analyst/analyst/schemas.py` (append)
- Create: `src/perpetual_analyst/analyst/prompts/digest.md`
- Test: `tests/test_schemas.py` (append)

- [ ] **Step 1: failing test** (append to `tests/test_schemas.py`):

```python
def test_digest_output_schema_is_provider_safe():
    from perpetual_analyst.analyst.schemas import DigestOutput

    schema = json.dumps(DigestOutput.model_json_schema())
    assert '"minimum"' not in schema and '"maximum"' not in schema
    out = DigestOutput(executive_summary="s", digest_text="d")
    assert out.digest_text == "d"
```

- [ ] **Step 2: run, expect ImportError**

- [ ] **Step 3: implement** — append to `schemas.py`:

```python
class DigestOutput(BaseModel):
    """Daily digest call output — one call per day (sanctioned Invariant 1 extension)."""

    executive_summary: str = Field(
        description="3-6 sentences, cross-topic, for the report's Executive summary section."
    )
    digest_text: str = Field(
        description=(
            "Telegram-ready digest, at most 3000 characters, first-person analyst voice. "
            "Structure: exec summary, top 3 developments with why-it-matters, "
            "thesis changes if any, watch next."
        )
    )
```

Create `src/perpetual_analyst/analyst/prompts/digest.md`:

```markdown
# Daily Digest Writer

You are the same analyst who wrote today's topic sections. Compose the daily digest
from the sections provided.

Rules:

1. **First person, confident, terse.** "I'm raising my confidence on X; yesterday's
   filing is the third signal this month." The digest is you talking, not a table of
   contents.
2. **executive_summary**: 3-6 sentences, cross-topic, judgment-first — what actually
   changed and what you now believe differently.
3. **digest_text**: at most 3,000 characters. Structure: one-line 🎯 summary, then the
   top 3 developments (one line each + why it matters), thesis changes if any
   (confidence before → after), then "Watch next". Use plain text with minimal HTML
   (<b>, <i> only). No headers, no exhaustive per-topic coverage — editorial judgment
   of what the reader must see.
4. If every topic reported nothing significant, say so in one line and stop. Do not
   manufacture significance.
5. Never restate yesterday's content unless its meaning changed today.
```

- [ ] **Step 4: run, green** (schemas tests + full suite)
- [ ] **Step 5: commit** (cross TODO 9 sub-item 3)

```powershell
git add src/perpetual_analyst/analyst/schemas.py src/perpetual_analyst/analyst/prompts/digest.md tests/test_schemas.py TODO.md
git commit -m "feat: DigestOutput schema and digest prompt"
```

---

### Task 3: `assemble_report` + `persist_report` (TODO 9 sub-items 1 + 4)

**Files:**
- Create: `src/perpetual_analyst/report/assemble.py` (replace stub)
- Create: `tests/test_assemble.py`

- [ ] **Step 1: failing tests** — create `tests/test_assemble.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from perpetual_analyst.analyst.schemas import DigestOutput, TopicAnalysis
from perpetual_analyst.report.assemble import assemble_report, persist_report
from perpetual_analyst.store.models import Topic


def _analysis(section="## What's new\nThings happened.", nothing=False, **kw):
    return TopicAnalysis(
        report_section_markdown=section,
        nothing_significant=nothing,
        **kw,
    )


def _digest_client(executive_summary="Exec.", digest_text="Digest."):
    parsed = DigestOutput(executive_summary=executive_summary, digest_text=digest_text)
    message = MagicMock()
    message.parsed = parsed
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.beta.chat.completions.parse.return_value = response
    return client


def test_assemble_merges_sections_and_digest(db, sample_topic, settings):
    digest_text, full = assemble_report(
        [(sample_topic, _analysis(open_questions=["Q1?"], watch_next=["W1"]))],
        db,
        _digest_client(),
        settings,
        "2026-06-12",
    )
    assert digest_text == "Digest."
    assert "# Daily Intelligence Brief — 2026-06-12" in full
    assert "## Executive summary" in full and "Exec." in full
    assert f"## Topic: {sample_topic.name}" in full
    assert "Things happened." in full
    assert "## Open questions" in full and "Q1?" in full
    assert "## Things to watch next" in full and "W1" in full


def test_nothing_significant_topic_gets_one_line(db, sample_topic, settings):
    _, full = assemble_report(
        [(sample_topic, _analysis(section="", nothing=True))],
        db,
        _digest_client(),
        settings,
        "2026-06-12",
    )
    assert f"*{sample_topic.name}: nothing significant today.*" in full
    assert "## What's new" not in full


def test_empty_optional_sections_omitted(db, sample_topic, settings):
    _, full = assemble_report(
        [(sample_topic, _analysis())], db, _digest_client(), settings, "2026-06-12"
    )
    assert "## Open questions" not in full
    assert "## Things to watch next" not in full


def test_digest_failure_falls_back(db, sample_topic, settings):
    client = MagicMock()
    client.beta.chat.completions.parse.side_effect = RuntimeError("api down")
    digest_text, full = assemble_report(
        [(sample_topic, _analysis())], db, client, settings, "2026-06-12"
    )
    assert "Things happened." in digest_text  # mechanical fallback
    assert "## Executive summary" not in full


def test_citations_rendered_in_full_report(db, sample_topic, sample_source, settings):
    cur = db.execute(
        "INSERT INTO items (source_id, content_hash, title, url)"
        " VALUES (?, 'h1', 'Cited Post', 'https://example.com/c')",
        (sample_source,),
    )
    db.commit()
    analysis = _analysis(section=f"Confirmed by [item:{cur.lastrowid}].")
    _, full = assemble_report(
        [(sample_topic, analysis)], db, _digest_client(), settings, "2026-06-12"
    )
    assert "[^1]" in full and "Cited Post" in full


def test_todays_thesis_updates_appended(db, sample_topic, settings):
    db.execute(
        "INSERT INTO theses (topic_id, statement, confidence, status)"
        " VALUES (?, 'T1 statement', 0.7, 'active')",
        (sample_topic.id,),
    )
    thesis_id = db.execute("SELECT id FROM theses").fetchone()["id"]
    db.execute(
        "INSERT INTO thesis_updates (thesis_id, change, confidence_before, confidence_after)"
        " VALUES (?, 'Raised on new signal.', 0.5, 0.7)",
        (thesis_id,),
    )
    db.commit()
    _, full = assemble_report(
        [(sample_topic, _analysis())],
        db,
        _digest_client(),
        settings,
        db.execute("SELECT date('now')").fetchone()[0],
    )
    assert "### Thesis updates" in full
    assert "0.50 → 0.70" in full


def test_persist_report_writes_row_and_file(db, tmp_path):
    report_id = persist_report(
        "2026-06-12", "digest", "# Full", db, reports_dir=str(tmp_path)
    )
    row = db.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    assert row["report_date"] == "2026-06-12"
    assert row["delivered_at"] is None
    assert (tmp_path / "brief-2026-06-12.md").read_text(encoding="utf-8") == "# Full"


def test_persist_duplicate_date_raises(db, tmp_path):
    persist_report("2026-06-12", "d", "f", db, reports_dir=str(tmp_path))
    with pytest.raises(Exception):
        persist_report("2026-06-12", "d", "f", db, reports_dir=str(tmp_path))
```

- [ ] **Step 2: run, expect ImportError**

- [ ] **Step 3: implement** — replace `src/perpetual_analyst/report/assemble.py`:

```python
"""Merge per-topic sections into the daily report; one digest call per day. See SPEC §9."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import openai

from perpetual_analyst.analyst.schemas import DigestOutput, TopicAnalysis
from perpetual_analyst.analyst.theses import render_thesis_fragment
from perpetual_analyst.config import Settings
from perpetual_analyst.report.render import render_citations
from perpetual_analyst.store.models import Thesis, ThesisUpdate, Topic

_DIGEST_PROMPT_PATH = Path(__file__).parent.parent / "analyst" / "prompts" / "digest.md"
_FALLBACK_DIGEST_CHARS = 3000


def _todays_thesis_pairs(
    topic_id: int, report_date: str, conn: sqlite3.Connection
) -> list[tuple[Thesis, ThesisUpdate]]:
    updates = conn.execute(
        """SELECT u.* FROM thesis_updates u
           JOIN theses t ON t.id = u.thesis_id
           WHERE t.topic_id = ? AND date(u.created_at) = ?
           ORDER BY u.id""",
        (topic_id, report_date),
    ).fetchall()
    pairs = []
    for update_row in updates:
        thesis_row = conn.execute(
            "SELECT * FROM theses WHERE id = ?", (update_row["thesis_id"],)
        ).fetchone()
        pairs.append((Thesis.from_row(thesis_row), ThesisUpdate.from_row(update_row)))
    return pairs


def _generate_digest(
    sections_text: str, client: openai.OpenAI, settings: Settings
) -> DigestOutput | None:
    try:
        extra = {"thinking": {"type": "adaptive"}} if settings.analyst.thinking else {}
        response = client.beta.chat.completions.parse(
            model=settings.analyst.id,
            messages=[
                {"role": "system", "content": _DIGEST_PROMPT_PATH.read_text(encoding="utf-8")},
                {"role": "user", "content": sections_text},
            ],
            response_format=DigestOutput,
            extra_body=extra,
        )
        return response.choices[0].message.parsed
    except Exception as exc:
        print(f"[report] digest call failed: {type(exc).__name__}")
        return None


def assemble_report(
    topic_results: list[tuple[Topic, TopicAnalysis]],
    conn: sqlite3.Connection,
    client: openai.OpenAI,
    settings: Settings,
    report_date: str,
) -> tuple[str, str]:
    """Returns (digest_text, full_markdown). One digest LLM call; mechanical fallback."""
    topic_blocks: list[str] = []
    for topic, analysis in topic_results:
        lines = [f"## Topic: {topic.name}", ""]
        if analysis.nothing_significant:
            lines.append(f"*{topic.name}: nothing significant today.*")
        else:
            lines.append(analysis.report_section_markdown)
            fragment = render_thesis_fragment(
                _todays_thesis_pairs(topic.id, report_date, conn)
            )
            if fragment:
                lines += ["", fragment]
        topic_blocks.append("\n".join(lines))

    sections_text = "\n\n".join(topic_blocks)
    digest = _generate_digest(sections_text, client, settings)

    parts = [f"# Daily Intelligence Brief — {report_date}", ""]
    if digest is not None and digest.executive_summary:
        parts += ["## Executive summary", "", digest.executive_summary, ""]
    parts.append(sections_text)

    open_questions = [q for _, a in topic_results for q in a.open_questions]
    if open_questions:
        parts += ["", "## Open questions", ""] + [f"- {q}" for q in open_questions]
    watch_next = [w for _, a in topic_results for w in a.watch_next]
    if watch_next:
        parts += ["", "## Things to watch next", ""] + [f"- {w}" for w in watch_next]

    full_markdown = render_citations("\n".join(parts), conn)
    digest_text = (
        digest.digest_text if digest is not None else sections_text[:_FALLBACK_DIGEST_CHARS]
    )
    return digest_text, full_markdown


def persist_report(
    report_date: str,
    digest_text: str,
    full_markdown: str,
    conn: sqlite3.Connection,
    reports_dir: str = "data/reports",
) -> int:
    """INSERT (UNIQUE report_date raises loudly on a bypassed per-day guard) + write file."""
    cur = conn.execute(
        "INSERT INTO reports (user_id, report_date, digest_text, full_markdown)"
        " VALUES (NULL, ?, ?, ?)",
        (report_date, digest_text, full_markdown),
    )
    conn.commit()
    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"brief-{report_date}.md").write_text(full_markdown, encoding="utf-8")
    return cur.lastrowid
```

- [ ] **Step 4: run, 8 passed; full suite green**
- [ ] **Step 5: commit** (cross TODO 9 sub-items 1 + 4 — Task 9 fully crossed)

```powershell
git add src/perpetual_analyst/report/assemble.py tests/test_assemble.py TODO.md
git commit -m "feat: daily report assembly with digest call, fallback, and persistence"
```

---

### Task 4: `select_analyst_items` + reactivation reset + smoke-test switch (handoff extension)

**Orchestrator: run `gitnexus_impact({target: "sync_config", direction: "upstream"})` first.** Log this task in TODO.md as: `- [ ] (extension 2026-06-12, handoff) select_analyst_items helper + fetch_error_count reset on reactivation + smoke test topic-scoping` under Task 10 before starting.

**Files:**
- Modify: `src/perpetual_analyst/analyst/triage.py` (append)
- Modify: `src/perpetual_analyst/config.py` (source-UPDATE branch)
- Modify: `tests/test_triage.py`, `tests/test_config.py` (append), `tests/test_smoke.py` (selection switch)

- [ ] **Step 1: failing tests**

Append to `tests/test_triage.py`:

```python
def test_select_analyst_items_scopes_by_topic(db, sample_topic, sample_source, settings):
    from perpetual_analyst.analyst.triage import select_analyst_items

    db.execute(
        "INSERT INTO topic_sources (topic_id, source_id) VALUES (?, ?)",
        (sample_topic.id, sample_source),
    )
    db.execute("INSERT INTO sources (type, name) VALUES ('rss', 'Other Source')")
    other_source = db.execute("SELECT id FROM sources WHERE name='Other Source'").fetchone()["id"]
    db.execute(
        "INSERT INTO items (source_id, content_hash, title, triage_score, status)"
        " VALUES (?, 'h_in', 'In Topic', 0.9, 'new')",
        (sample_source,),
    )
    db.execute(
        "INSERT INTO items (source_id, content_hash, title, triage_score, status)"
        " VALUES (?, 'h_out', 'Other Topic', 0.9, 'new')",
        (other_source,),
    )
    db.execute(
        "INSERT INTO items (source_id, content_hash, title, triage_score, status)"
        " VALUES (?, 'h_skip', 'Skipped', 0.9, 'skipped')",
        (sample_source,),
    )
    db.execute(
        "INSERT INTO items (source_id, content_hash, title, triage_score, status)"
        " VALUES (?, 'h_low', 'Low', 0.1, 'new')",
        (sample_source,),
    )
    db.commit()
    items = select_analyst_items(sample_topic.id, db)
    assert [i.title for i in items] == ["In Topic"]


def test_select_analyst_items_orders_and_limits(db, sample_topic, sample_source, settings):
    from perpetual_analyst.analyst.triage import select_analyst_items

    db.execute(
        "INSERT INTO topic_sources (topic_id, source_id) VALUES (?, ?)",
        (sample_topic.id, sample_source),
    )
    for i, score in enumerate((0.3, 0.9, 0.6)):
        db.execute(
            "INSERT INTO items (source_id, content_hash, title, triage_score)"
            " VALUES (?, ?, ?, ?)",
            (sample_source, f"h{i}", f"Item{score}", score),
        )
    db.commit()
    items = select_analyst_items(sample_topic.id, db, limit=2)
    assert [i.triage_score for i in items] == [0.9, 0.6]
```

Append to `tests/test_config.py`:

```python
def test_reactivated_source_resets_error_count(db):
    sync_config(db, [_topic()], [_source()])
    db.execute("UPDATE sources SET active = 0, fetch_error_count = 5")
    db.commit()
    sync_config(db, [_topic()], [_source()])
    row = db.execute("SELECT active, fetch_error_count FROM sources").fetchone()
    assert row["active"] == 1
    assert row["fetch_error_count"] == 0


def test_still_active_source_keeps_error_count(db):
    sync_config(db, [_topic()], [_source()])
    db.execute("UPDATE sources SET fetch_error_count = 3")
    db.commit()
    sync_config(db, [_topic()], [_source()])
    assert db.execute("SELECT fetch_error_count FROM sources").fetchone()[0] == 3
```

- [ ] **Step 2: run, expect ImportError/failures**

- [ ] **Step 3: implement**

Append to `triage.py`:

```python
def select_analyst_items(
    topic_id: int, conn: sqlite3.Connection, limit: int = 10
) -> list[Item]:
    """Items the analyst should see today: triaged, kept, topic-scoped, best first."""
    rows = conn.execute(
        """SELECT i.* FROM items i
           JOIN topic_sources ts ON ts.source_id = i.source_id AND ts.topic_id = ?
           WHERE i.status = 'new' AND i.triage_score >= ?
           ORDER BY i.triage_score DESC
           LIMIT ?""",
        (topic_id, SKIP_THRESHOLD, limit),
    ).fetchall()
    return [Item.from_row(row) for row in rows]
```

In `config.py` `sync_config`, change the source SELECT to fetch `id, active` and reset the counter on reactivation:

```python
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
                conn.execute(
                    "UPDATE sources SET fetch_error_count = 0 WHERE id = ?", (source_id,)
                )
```

In `tests/test_smoke.py`, replace the `keep = [...]` SELECT block with:

```python
    from perpetual_analyst.analyst.triage import select_analyst_items

    keep = select_analyst_items(topic.id, conn, limit=MAX_ANALYST_ITEMS)
```
(move the import to the top imports; drop the now-unused `SKIP_THRESHOLD` import if nothing else uses it.)

- [ ] **Step 4: run full suite, green (smoke still deselected)**
- [ ] **Step 5: commit** (cross the extension TODO line)

```powershell
git add src/perpetual_analyst/analyst/triage.py src/perpetual_analyst/config.py tests/test_triage.py tests/test_config.py tests/test_smoke.py TODO.md
git commit -m "feat: shared select_analyst_items and error-count reset on source reactivation"
```

---

### Task 5: Telegram delivery (TODO 10 sub-items 1 + 2)

**Files:**
- Create: `src/perpetual_analyst/delivery/telegram.py` (replace stub)
- Create: `tests/test_telegram.py`

- [ ] **Step 1: failing tests** — create `tests/test_telegram.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from perpetual_analyst.delivery import telegram
from perpetual_analyst.store.models import Report


def _report(db, report_date="2026-06-12", digest="hello <b>world</b>"):
    cur = db.execute(
        "INSERT INTO reports (report_date, digest_text, full_markdown) VALUES (?, ?, ?)",
        (report_date, digest, "# Full report"),
    )
    db.commit()
    row = db.execute("SELECT * FROM reports WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Report.from_row(row)


@pytest.fixture
def tg_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")


@pytest.fixture
def sent(monkeypatch):
    calls = AsyncMock()
    monkeypatch.setattr(telegram, "_send", calls)
    return calls


def test_missing_env_skips_without_raising(db, monkeypatch, capsys):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    report = _report(db)
    assert telegram.send_report(report, db) is False
    row = db.execute("SELECT delivered_at FROM reports").fetchone()
    assert row["delivered_at"] is None
    assert "skipping delivery" in capsys.readouterr().out


def test_successful_send_stamps_delivered(db, tg_env, sent):
    report = _report(db)
    assert telegram.send_report(report, db) is True
    row = db.execute("SELECT delivered_at FROM reports").fetchone()
    assert row["delivered_at"] is not None


def test_send_failure_leaves_undelivered_and_no_token_in_output(db, tg_env, monkeypatch, capsys):
    async def _boom(*args, **kwargs):
        raise RuntimeError("secret-token leaked? no")

    monkeypatch.setattr(telegram, "_send", _boom)
    report = _report(db)
    assert telegram.send_report(report, db) is False
    assert db.execute("SELECT delivered_at FROM reports").fetchone()["delivered_at"] is None
    out = capsys.readouterr().out
    assert "secret-token" not in out


def test_retry_undelivered_delivers_backlog(db, tg_env, sent):
    _report(db, "2026-06-10")
    _report(db, "2026-06-11")
    delivered = db.execute(
        "INSERT INTO reports (report_date, digest_text, full_markdown, delivered_at)"
        " VALUES ('2026-06-09', 'd', 'f', datetime('now'))"
    )
    db.commit()
    assert telegram.retry_undelivered(db) == 2
    remaining = db.execute(
        "SELECT COUNT(*) FROM reports WHERE delivered_at IS NULL"
    ).fetchone()[0]
    assert remaining == 0


def test_digest_truncated_at_paragraph(db, tg_env, sent):
    long_digest = ("para one\n\n" + "x" * 4000)
    report = _report(db, digest=long_digest)
    telegram.send_report(report, db)
    sent_digest = sent.call_args.args[2]
    assert len(sent_digest) <= telegram.DIGEST_CHAR_LIMIT
    assert sent_digest.startswith("para one")
```

- [ ] **Step 2: run, expect ImportError**

- [ ] **Step 3: implement** — replace `src/perpetual_analyst/delivery/telegram.py`:

```python
"""Telegram send: HTML digest (<=3,000 chars) + .md attachment. Send-only V1. See SPEC §10."""

from __future__ import annotations

import asyncio
import io
import os
import sqlite3

from telegram import Bot

from perpetual_analyst.store.models import Report

DIGEST_CHAR_LIMIT = 3000


def _truncate_at_paragraph(text: str, limit: int = DIGEST_CHAR_LIMIT) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    boundary = cut.rfind("\n\n")
    return cut[:boundary] if boundary > 0 else cut


async def _send(token: str, chat_id: str, digest: str, report: Report) -> None:
    bot = Bot(token=token)
    async with bot:
        await bot.send_message(chat_id=chat_id, text=digest, parse_mode="HTML")
        await bot.send_document(
            chat_id=chat_id,
            document=io.BytesIO((report.full_markdown or "").encode("utf-8")),
            filename=f"brief-{report.report_date}.md",
        )


def send_report(report: Report, conn: sqlite3.Connection) -> bool:
    """Deliver one report; stamps delivered_at on success. Env-gated, never raises."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[telegram] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set - skipping delivery")
        return False

    digest = _truncate_at_paragraph(report.digest_text or "")
    try:
        asyncio.run(_send(token, chat_id, digest, report))
    except Exception as exc:
        # exception text could embed the token (e.g. request URLs) - print type only
        print(f"[telegram] send failed for {report.report_date}: {type(exc).__name__}")
        return False

    conn.execute(
        "UPDATE reports SET delivered_at = datetime('now') WHERE id = ?", (report.id,)
    )
    conn.commit()
    return True


def retry_undelivered(conn: sqlite3.Connection) -> int:
    """Send every report with delivered_at IS NULL; returns count delivered."""
    rows = conn.execute(
        "SELECT * FROM reports WHERE delivered_at IS NULL ORDER BY report_date"
    ).fetchall()
    return sum(1 for row in rows if send_report(Report.from_row(row), conn))
```

Note: `test_successful_send_stamps_delivered` monkeypatches `_send` with `AsyncMock` — `asyncio.run(AsyncMock()(...))` works because AsyncMock returns a coroutine. If it errors, use a plain `async def _ok(*a, **kw): return None`.

- [ ] **Step 4: run, 5 passed; full suite green**
- [ ] **Step 5: commit** (cross TODO 10 sub-items 1 + 2)

```powershell
git add src/perpetual_analyst/delivery/telegram.py tests/test_telegram.py TODO.md
git commit -m "feat: env-gated Telegram delivery with paragraph truncation and retry"
```

---

### Task 6: `daily_run` orchestrator + `analyst run` CLI (TODO 10 sub-item 3)

**Orchestrator: run `gitnexus_impact({target: "run", direction: "upstream"})` (cli stub) first — expected LOW.**

**Files:**
- Create: `src/perpetual_analyst/daily_run.py` (replace stub)
- Modify: `src/perpetual_analyst/cli.py` (`run` command)
- Create: `tests/test_daily_run.py`

- [ ] **Step 1: failing tests** — create `tests/test_daily_run.py` (pure orchestration tests; every stage monkeypatched):

```python
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from perpetual_analyst import daily_run
from perpetual_analyst.store.models import Topic


@pytest.fixture
def two_topics(db):
    db.execute("INSERT INTO topics (user_id, slug, name, active) VALUES (1, 'a', 'A', 1)")
    db.execute("INSERT INTO topics (user_id, slug, name, active) VALUES (1, 'b', 'B', 1)")
    db.execute("INSERT INTO topics (user_id, slug, name, active) VALUES (1, 'off', 'Off', 0)")
    db.commit()
    return db


@pytest.fixture
def quiet_stages(monkeypatch):
    """Neutralize all pipeline stages; tests re-patch what they assert on."""
    monkeypatch.setattr(daily_run, "load_topics", lambda: [])
    monkeypatch.setattr(daily_run, "load_sources", lambda: [])
    monkeypatch.setattr(daily_run, "sync_config", MagicMock())
    monkeypatch.setattr(daily_run, "fetch_rss", MagicMock(return_value=0))
    monkeypatch.setattr(daily_run, "scan_inbox", MagicMock(return_value=[]))
    monkeypatch.setattr(daily_run, "triage_items", MagicMock(return_value=[]))
    monkeypatch.setattr(daily_run, "select_analyst_items", MagicMock(return_value=[]))
    monkeypatch.setattr(daily_run, "run_topic", MagicMock(return_value=None))
    monkeypatch.setattr(
        daily_run, "assemble_report", MagicMock(return_value=("digest", "full"))
    )
    monkeypatch.setattr(daily_run, "persist_report", MagicMock(return_value=1))
    monkeypatch.setattr(daily_run, "retry_undelivered", MagicMock(return_value=0))
    return monkeypatch


def test_failing_topic_does_not_kill_run(two_topics, quiet_stages, settings):
    analysis = MagicMock()
    calls = []

    def _run_topic(topic, items, conn, client, s, dry_run=False):
        calls.append(topic.slug)
        if topic.slug == "a":
            raise RuntimeError("boom")
        return analysis

    quiet_stages.setattr(daily_run, "run_topic", _run_topic)
    daily_run.run_daily(two_topics, MagicMock(), settings)
    assert calls == ["a", "b"]
    # assembly still ran with the surviving topic
    assert daily_run.assemble_report.call_count == 1
    (results, *_), _ = daily_run.assemble_report.call_args
    assert [t.slug for t, _ in results] == ["b"]


def test_per_day_guard_skips_analysis_but_retries_delivery(two_topics, quiet_stages, settings):
    two_topics.execute(
        "INSERT INTO reports (report_date, digest_text) VALUES (date('now'), 'd')"
    )
    two_topics.commit()
    daily_run.run_daily(two_topics, MagicMock(), settings)
    assert daily_run.run_topic.call_count == 0
    assert daily_run.assemble_report.call_count == 0
    assert daily_run.retry_undelivered.call_count == 1


def test_topic_filter(two_topics, quiet_stages, settings):
    analysis = MagicMock()
    quiet_stages.setattr(
        daily_run, "run_topic", MagicMock(return_value=analysis)
    )
    daily_run.run_daily(two_topics, MagicMock(), settings, topic_slug="b")
    assert daily_run.run_topic.call_count == 1
    topic_arg = daily_run.run_topic.call_args.args[0]
    assert topic_arg.slug == "b"


def test_dry_run_skips_triage_assembly_and_delivery(two_topics, quiet_stages, settings):
    quiet_stages.setattr(
        daily_run, "select_analyst_items", MagicMock(return_value=[MagicMock()])
    )
    daily_run.run_daily(two_topics, None, settings, dry_run=True)
    assert daily_run.triage_items.call_count == 0
    assert daily_run.assemble_report.call_count == 0
    assert daily_run.persist_report.call_count == 0
    assert daily_run.retry_undelivered.call_count == 0
    assert daily_run.run_topic.call_count == 2  # dry prompts still printed


def test_no_results_skips_assembly(two_topics, quiet_stages, settings):
    daily_run.run_daily(two_topics, MagicMock(), settings)
    assert daily_run.assemble_report.call_count == 0
    assert daily_run.retry_undelivered.call_count == 1
```

- [ ] **Step 2: run, expect failures** (stub has no `run_daily`)

- [ ] **Step 3: implement** — replace `src/perpetual_analyst/daily_run.py`:

```python
"""Daily pipeline orchestrator: sync -> ingest -> triage -> analyze -> assemble -> deliver.

Entry point: python -m perpetual_analyst.daily_run
Per-stage and per-topic failures are isolated: one broken topic or stage never
kills the rest of the run. Exit 0 even on partial success (SPEC §12 Phase 3).
"""

from __future__ import annotations

import sqlite3

import openai
from dotenv import load_dotenv

from perpetual_analyst.analyst.agent import make_client, run_topic
from perpetual_analyst.analyst.triage import select_analyst_items, triage_items
from perpetual_analyst.config import Settings, load_settings, load_sources, load_topics, sync_config
from perpetual_analyst.delivery.telegram import retry_undelivered
from perpetual_analyst.ingestion.inbox import scan_inbox
from perpetual_analyst.ingestion.rss import fetch_rss
from perpetual_analyst.report.assemble import assemble_report, persist_report
from perpetual_analyst.store.db import init_db
from perpetual_analyst.store.models import Item, Source, Topic


def _active_topics(conn: sqlite3.Connection) -> list[Topic]:
    rows = conn.execute("SELECT * FROM topics WHERE active = 1").fetchall()
    return [Topic.from_row(row) for row in rows]


def _topic_sources(topic_id: int, source_type: str, conn: sqlite3.Connection) -> list[Source]:
    rows = conn.execute(
        """SELECT s.* FROM sources s
           JOIN topic_sources ts ON ts.source_id = s.id
           WHERE ts.topic_id = ? AND s.type = ? AND s.active = 1""",
        (topic_id, source_type),
    ).fetchall()
    return [Source.from_row(row) for row in rows]


def _untriaged_items(topic_id: int, conn: sqlite3.Connection) -> list[Item]:
    rows = conn.execute(
        """SELECT i.* FROM items i
           JOIN topic_sources ts ON ts.source_id = i.source_id AND ts.topic_id = ?
           WHERE i.status = 'new' AND i.triage_score IS NULL""",
        (topic_id,),
    ).fetchall()
    return [Item.from_row(row) for row in rows]


def run_daily(
    conn: sqlite3.Connection,
    client: openai.OpenAI | None,
    settings: Settings,
    topic_slug: str | None = None,
    dry_run: bool = False,
) -> None:
    try:
        sync_config(conn, load_topics(), load_sources())
    except Exception as exc:
        print(f"[daily] config sync failed: {exc}")

    topics = _active_topics(conn)
    if topic_slug:
        topics = [t for t in topics if t.slug == topic_slug]

    for topic in topics:
        for source in _topic_sources(topic.id, "inbox", conn):
            try:
                scan_inbox(topic.slug, topic.id, source.id, conn)
            except Exception as exc:
                print(f"[daily] inbox scan failed for {topic.slug}: {exc}")
        for source in _topic_sources(topic.id, "rss", conn):
            try:
                fetch_rss(source, conn)
            except Exception as exc:
                print(f"[daily] rss fetch failed for {source.name}: {exc}")

    already = conn.execute(
        "SELECT 1 FROM reports WHERE report_date = date('now')"
    ).fetchone()
    if already:
        print("[daily] report for today already exists - skipping analysis")
    else:
        results: list[tuple[Topic, object]] = []
        for topic in topics:
            try:
                pending = _untriaged_items(topic.id, conn)
                if pending and not dry_run:
                    triage_items(pending, topic.brief or "", client, settings, conn)
                keep = select_analyst_items(topic.id, conn)
                analysis = run_topic(topic, keep, conn, client, settings, dry_run=dry_run)
                if analysis is not None:
                    results.append((topic, analysis))
            except Exception as exc:
                print(f"[daily] topic {topic.slug} failed: {exc}")

        if not dry_run and results:
            try:
                report_date = conn.execute("SELECT date('now')").fetchone()[0]
                digest_text, full_markdown = assemble_report(
                    results, conn, client, settings, report_date
                )
                persist_report(report_date, digest_text, full_markdown, conn)
            except Exception as exc:
                print(f"[daily] assemble/persist failed: {exc}")

    if not dry_run:
        try:
            delivered = retry_undelivered(conn)
            print(f"[daily] delivered {delivered} report(s)")
        except Exception as exc:
            print(f"[daily] delivery stage failed: {exc}")


def main() -> None:
    load_dotenv()
    conn = init_db()
    try:
        run_daily(conn, make_client(), load_settings())
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

In `cli.py`, replace the `run` stub:

```python
@app.command()
def run(
    topic: str = typer.Option(None, help="Topic slug to run (default: all active)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print prompt, skip API calls"),
    db_path: str = typer.Option("data/analyst.db", help="SQLite DB path"),
) -> None:
    """Run the daily analyst pipeline."""
    from perpetual_analyst.analyst.agent import make_client
    from perpetual_analyst.config import load_settings
    from perpetual_analyst.daily_run import run_daily

    conn = init_db(db_path)
    try:
        client = None if dry_run else make_client()
        run_daily(conn, client, load_settings(), topic_slug=topic, dry_run=dry_run)
    finally:
        conn.close()
```

(Function-level imports keep `daily_run`'s heavier import graph off the CLI's add/list paths — acceptable deviation from top-level-imports style; note it in the commit.)

- [ ] **Step 4: run, 5 passed; full suite green**
- [ ] **Step 5: manual validation** — from the worktree root with PYTHONPATH set:

```powershell
C:\Users\rvind\OneDrive\Desktop\Projects\perpetual-analyst\.venv\Scripts\python -m perpetual_analyst.cli run --dry-run --db-path data/dry-run-test.db
```
Expected: config syncs, feeds fetch (network), prompts print, zero API calls, no report/delivery. Delete `data/dry-run-test.db*` afterwards. If feed fetching makes this annoyingly slow, run with `--topic ai-frontier-labs` and accept the wait — do NOT skip the validation.

- [ ] **Step 6: commit** (cross TODO 10 sub-item 3)

```powershell
git add src/perpetual_analyst/daily_run.py src/perpetual_analyst/cli.py tests/test_daily_run.py TODO.md
git commit -m "feat: daily_run orchestrator with per-stage isolation and analyst run CLI"
```

---

### Task 7: Scheduler documentation (TODO 10 sub-item 4)

**Files:**
- Modify: `docs/commands.md`

- [ ] **Step 1: add a "Scheduling the daily run" section** to `docs/commands.md` (match the doc's existing heading style):

```markdown
## Scheduling the daily run

The pipeline is `python -m perpetual_analyst.daily_run` executed from the repo root
(it reads `config/*.yaml`, `.env`, and `data/analyst.db` relative to the working
directory).

**Windows (Task Scheduler):**

```powershell
schtasks /Create /SC DAILY /ST 06:30 /TN "PerpetualAnalyst" `
  /TR "cmd /c cd /d C:\path\to\perpetual-analyst && .venv\Scripts\python -m perpetual_analyst.daily_run"
```

**Linux (cron):**

```cron
30 6 * * * cd /path/to/perpetual-analyst && .venv/bin/python -m perpetual_analyst.daily_run >> data/daily_run.log 2>&1
```

Notes: the working directory must be the repo root; failed Telegram deliveries are
retried on the next run; a second run on the same day skips analysis (per-day guard)
and only retries delivery.
```

- [ ] **Step 2: pre-commit green; commit** (cross TODO 10 sub-item 4 — Task 10 fully crossed)

```powershell
git add docs/commands.md TODO.md
git commit -m "docs: scheduler entries for Windows Task Scheduler and cron"
```

---

## Spec coverage check

| Spec element | Task |
|---|---|
| render_citations | 1 |
| DigestOutput + digest.md | 2 |
| assemble_report / persist_report / thesis fragment wiring | 3 |
| select_analyst_items + reactivation reset + smoke switch | 4 |
| telegram send/retry/truncation/env-gating | 5 |
| daily_run pipeline + per-day guard + CLI | 6 |
| scheduler docs | 7 |

## TODO sub-item → task map

| TODO | Plan task |
|---|---|
| 9.1 assemble.py | 3 |
| 9.2 render.py | 1 |
| 9.3 digest.md | 2 |
| 9.4 reports row + file | 3 |
| 10.1 telegram.py | 5 |
| 10.2 retry logic | 5 |
| 10.3 daily_run orchestrator | 6 |
| 10.4 scheduler docs | 7 |
| handoff extension | 4 |
