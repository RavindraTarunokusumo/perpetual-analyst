# Firecrawl Source Extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use Grok junior handoff per `AGENTS.md` §Grok Build
> Implementation/Review Handoff, or fall back to direct implementation with reason logged in
> `TODO.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify URL article extraction through `extract_url()` with trafilatura-first and
Firecrawl `/scrape` fallback for bot-protected pages.

**Architecture:** Single entry point in `extract.py`; `rss.py` delegates to it; Firecrawl called
only on bot-wall or short-content failure when `FIRECRAWL_API_KEY` is set.

**Tech Stack:** Python 3.11+, httpx, trafilatura, firecrawl-py, pytest.

**Spec:** `docs/specs/2026-07-08-firecrawl-source-extraction.md`

## Global Constraints

- `_MIN_ARTICLE_CHARS = 200` on both trafilatura and Firecrawl paths.
- `FIRECRAWL_API_KEY` never logged (invariant #7).
- RSS item-level extraction failure → feed summary fallback; no `fetch_error_count` bump.
- `content_hash` dedupe unchanged (invariant #8).
- Worktree: `.worktree/firecrawl-source-extraction`, branch `firecrawl-source-extraction`.
- Reinstall editable package after worktree switch: `pip install -e ".[dev]"`.
- Pre-commit from repo root; specific staging only (`git add <files>`).
- One commit per task sub-item.

---

## File map

```
src/perpetual_analyst/ingestion/
  extract.py          CHG  Firecrawl fallback in extract_url (T2)
  rss.py              CHG  delegate to extract_url (T3)
pyproject.toml        CHG  add firecrawl-py (T1)
.env.example          CHG  FIRECRAWL_API_KEY (T1)
AGENTS.md             CHG  never-log list (T1)
CLAUDE.md             CHG  mirror AGENTS.md (T1)
tests/
  test_extract.py     CHG  Firecrawl fallback tests (T2)
  test_rss.py         CHG  mock extract_url (T3)
  test_extract_smoke.py  NEW  live smoke (T4)
scripts/pa_inspect.py  WIP  commit as T0 (already wired)
```

---

### Task T0: Commit carried WIP (trafilatura base)

**Files:**
- Modify: `src/perpetual_analyst/ingestion/extract.py`
- Modify: `scripts/pa_inspect.py`
- Create: `tests/test_extract.py`
- Modify: `src/perpetual_analyst/substrate.py` (orthogonal fix — separate commit)

**Interfaces:**
- Produces: `extract_url(url, *, timeout=30.0) -> FetchedArticle`
- Produces: `ArticleFetchError`, `FetchedArticle(title, text)`

- [ ] Run `pytest tests/test_extract.py -q` — 3 passed
- [ ] Commit extract + pa_inspect + tests (not substrate in same commit)
- [ ] Commit substrate fix separately: `get_or_create_watch_topic(name: str | None)`

---

### Task T1: Dependency + config

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `AGENTS.md`, `CLAUDE.md`

**Interfaces:**
- Produces: `firecrawl-py>=1.0.0` (or current stable) in dependencies
- Produces: `FIRECRAWL_API_KEY=` documented in `.env.example`

- [ ] Add `firecrawl-py` to `pyproject.toml` dependencies
- [ ] `pip install -e ".[dev]"` from worktree
- [ ] Add `FIRECRAWL_API_KEY=` to `.env.example` with comment
- [ ] Add `FIRECRAWL_API_KEY` to never-log list in `AGENTS.md` and `CLAUDE.md`
- [ ] Commit

---

### Task T2: Firecrawl fallback in `extract_url`

**Files:**
- Modify: `src/perpetual_analyst/ingestion/extract.py`
- Modify: `tests/test_extract.py`

**Interfaces:**
- Consumes: `FetchedArticle`, `ArticleFetchError`, `_looks_like_bot_wall`, `_MIN_ARTICLE_CHARS`
- Produces: `_scrape_with_firecrawl(url: str, *, timeout: float) -> FetchedArticle`
- Produces: `extract_url()` calls Firecrawl when trafilatura path fails bot-wall/short checks

- [ ] **Write failing test:** bot-wall HTML → mock Firecrawl returns markdown → success

```python
def test_extract_url_falls_back_to_firecrawl_on_bot_wall(monkeypatch):
    # httpx returns bot-wall HTML; trafilatura path fails
    # monkeypatch _scrape_with_firecrawl or Firecrawl client to return 300-char markdown
    ...
```

- [ ] **Write failing test:** bot-wall + no `FIRECRAWL_API_KEY` → `ArticleFetchError`

- [ ] **Write failing test:** Firecrawl returns short markdown → `ArticleFetchError`

- [ ] **Implement `_scrape_with_firecrawl`:**
  - lazy-import `Firecrawl`
  - read `os.environ.get("FIRECRAWL_API_KEY")`; if missing, raise `ArticleFetchError`
  - `client.scrape(url, formats=["markdown"], only_main_content=True)`
  - validate `len(markdown.strip()) >= _MIN_ARTICLE_CHARS`
  - return `FetchedArticle(title=metadata.title, text=markdown)`

- [ ] **Wire fallback in `extract_url`:**
  - after trafilatura bot-wall or short-content check fails, call `_scrape_with_firecrawl`
  - preserve existing error messages when Firecrawl also fails

- [ ] Run `pytest tests/test_extract.py -q` — all pass
- [ ] Commit

---

### Task T3: Wire `rss.py` to `extract_url`

**Files:**
- Modify: `src/perpetual_analyst/ingestion/rss.py`
- Modify: `tests/test_rss.py`

**Interfaces:**
- Consumes: `extract_url`, `ArticleFetchError` from `perpetual_analyst.ingestion.extract`
- Produces: `_extract_text(url, summary) -> str | None` — calls `extract_url`, falls back to summary

- [ ] Replace `_extract_text` body:

```python
def _extract_text(url: str | None, summary: str | None) -> str | None:
    if url:
        try:
            return extract_url(url).text
        except ArticleFetchError:
            pass
    return summary or None
```

- [ ] Remove unused `trafilatura` import from `rss.py`
- [ ] Update `test_rss.py` patches: `perpetual_analyst.ingestion.rss.extract_url` instead of `trafilatura.fetch_url`
- [ ] Add test: `extract_url` raises → item gets summary text
- [ ] Run `pytest tests/test_rss.py tests/test_extract.py -q`
- [ ] Commit

---

### Task T4: Live smoke test

**Files:**
- Create: `tests/test_extract_smoke.py`

**Interfaces:**
- Consumes: `extract_url`, real `FIRECRAWL_API_KEY` from `.env`
- Produces: `@pytest.mark.smoke` test skipped when key missing

- [ ] Add smoke test for a known bot-protected article URL (Reuters or similar)
- [ ] Skip when `FIRECRAWL_API_KEY` not set
- [ ] Assert `len(text) >= 200`
- [ ] Document in test docstring: `pytest -m smoke tests/test_extract_smoke.py`
- [ ] Commit

---

### Task T5: Final validation + docs touch-up

- [ ] `ruff check . --fix && ruff format .`
- [ ] `pytest` (full suite, smoke excluded by default)
- [ ] Update `docs/architecture.md` one-liner for `extract.py` (Firecrawl fallback note)
- [ ] Update `TODO.md` — mark session items complete, tag commit hashes
- [ ] Pre-PR: run review per workflow Step 5

---

## Grok handoff notes

Delegate **T2** and **T3** as separate Grok junior sessions. Each prompt must include:
- worktree path `.worktree/firecrawl-source-extraction`
- spec path `docs/specs/2026-07-08-firecrawl-source-extraction.md`
- exact files in scope
- `FetchedArticle` / `ArticleFetchError` signatures
- invariant #7 (never log `FIRECRAWL_API_KEY`)
- run `pytest` for touched tests before reporting done

T0/T1/T4/T5: senior dev direct (small, config, or validation).