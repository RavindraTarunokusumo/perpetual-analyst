# Phase 2 — Source Ingestion + Retrieval Design

**Date:** 2026-06-11
**Scope:** Tasks 6–8 from TODO.md (thesis lifecycle, RSS ingestion + triage, retrieval) plus an added config/CLI task
**Branch:** `phase-2-ingestion-retrieval`

This is the first of three sub-projects in this session (Phase 2 → Phase 3 → Web UI); each gets its own spec, plan, and PR.

---

## Decisions Locked In

| # | Decision | Choice |
|---|---|---|
| 1 | Thesis code location | CRUD + ≤7 enforcement stay in `memory.py` (the established transactional write path); `theses.py` adds only stale-flagging and report rendering |
| 2 | Triage batching | One batched LLM call per topic, chunked at 20 items per call; strict JSON array output, Pydantic-validated; one retry on parse failure, then chunk left untriaged (`status='new'`) |
| 3 | Triage model | `settings.triage.id` via the existing `make_client()` OpenRouter pattern — *not* hardcoded Haiku; SPEC's "Haiku" means "the configured cheap triage model" |
| 4 | Recency weighting | Single SQL query per helper: `bm25()` rank multiplied by a CASE recency boost (observations <30 days, items <14 days); no Python re-ranking |
| 5 | Config source of truth | YAML defines topics/sources; `sync_config()` upserts into DB (topics keyed on slug, sources on URL) at the start of every run; runtime state (`last_fetched_at`, `fetch_error_count`) lives only in DB |
| 6 | CLI scope | `analyst topic add` and `analyst source add` append to YAML then re-sync; no other commands this phase |
| 7 | Verification | Mocked unit tests + one `pytest -m smoke` live test (real AI-frontier-labs feeds, real triage call, one real analyst run) against a scratch DB, run once before PR |
| 8 | Feed fetching | `httpx` fetches feed bytes (30s timeout), `feedparser` parses them — explicit error counting instead of feedparser's silent network handling |

---

## Module Interfaces

### `analyst/theses.py` (Task 6)

```python
def get_stale_theses(topic_id: int, conn: sqlite3.Connection, days: int = 30) -> list[Thesis]
def render_thesis_fragment(theses_with_updates: list[tuple[Thesis, ThesisUpdate]]) -> str
```

- `get_stale_theses`: active theses where `COALESCE(updated_at, created_at)` is older than `days` days.
- `render_thesis_fragment`: markdown fragment for the report's "Thesis updates" section — one line per moved thesis with `confidence {before} → {after}` and the change rationale. Returns `""` when nothing moved (sections with nothing to say are omitted, SPEC §9).
- Thesis CRUD (`get_active_theses`, `apply_thesis_update`) remains in `memory.py`; `theses.py` imports from there. No duplication, no move.
- **Context wiring:** `assemble_context` (agent.py) gains a "Stale theses — revisit or retire" block listing output of `get_stale_theses`, after the active-theses block.
- The ≤7 active limit and audit-trail invariants already implemented in `memory.py` gain regression tests (8th thesis raises `ValueError`; every revision writes a `thesis_updates` row).

### `ingestion/rss.py` (Task 7a)

```python
def fetch_rss(source: Source, conn: sqlite3.Connection) -> int  # returns count of newly inserted items
```

- Fetch feed bytes with `httpx.get(source.url, timeout=30)`, parse with `feedparser.parse(bytes)`.
- Skip entries with a published/updated date older than `source.last_fetched_at`; when `last_fetched_at` is NULL (first fetch), take all entries. Entries without dates are taken (dedupe catches repeats).
- Full-article text via `trafilatura` (fetch + extract per entry link); on extraction failure fall back to the feed's own summary/description. Item-level extraction failure does **not** count as feed failure.
- All inserts go through `store.db.insert_item()` — the only safe item write path. `content_hash` dedupe silently skips duplicates (Invariant 8).
- On feed-level failure (HTTP error, timeout, unparseable feed): increment `sources.fetch_error_count`; when it reaches 5, set `active=0`. On success: reset `fetch_error_count` to 0 and stamp `last_fetched_at`.
- Caller loops sources with per-source try/except — one broken feed never blocks the rest.

### `analyst/triage.py` (Task 7b)

```python
class TriageResult(BaseModel):
    item_id: int
    score: float          # 0–1 relevance
    summary: str          # 2-line summary

def triage_items(
    items: list[Item],
    topic_brief: str,
    client: openai.OpenAI,
    settings: Settings,
    conn: sqlite3.Connection,
) -> list[TriageResult]
```

- Chunk items at 20 per call. Prompt per chunk: topic brief + numbered items (id, title, source name, first ~1,500 chars of `raw_text`).
- Response: strict JSON array of `{item_id, score, summary}`, validated against `list[TriageResult]`.
- Parse failure → one retry with the validation error appended to the prompt; second failure → log, leave chunk items `status='new'`, continue with remaining chunks.
- DB writes per validated result: set `triage_score`, `triage_summary`; `score < 0.2` → `status='skipped'`. Items ≥ 0.2 remain `new`; the analyst run marks them `analyzed`.

### `retrieval/search.py` (Task 8)

```python
def related_observations(text: str, topic_id: int, conn: sqlite3.Connection, k: int = 5) -> list[Observation]
def related_items(text: str, topic_id: int, conn: sqlite3.Connection, k: int = 3, exclude_ids: list[int] | None = None) -> list[Item]
```

- `related_observations`: `observations_fts MATCH`, joined to `observations` with `topic_id = ?` AND `status = 'active'`, ranked by `bm25(observations_fts) * CASE WHEN created_at >= datetime('now','-30 days') THEN 0.5 ELSE 1.0 END` (bm25 is lower-is-better, so the boost multiplies it down), `LIMIT k`.
- `related_items`: `items_fts MATCH`, joined through `sources`/`topic_sources` to filter by topic, excludes `exclude_ids` (the items currently being analyzed) and `status='skipped'` items, 14-day recency boost, `LIMIT k`.
- FTS query construction: split input text into terms, drop punctuation, wrap each term in double quotes, join with `OR` — guards against FTS5 query-syntax errors from arbitrary text.
- **Context wiring:** in `assemble_context`, for each triaged item build the query from `title + triage_summary` and attach a "Related prior context" block (top-5 observations as `[obs:ID]` lines, top-3 items as `[item:ID]` title lines, each truncated to one line). Items remain last in prompt order (caching-friendly ordering preserved).

### `config.py` + `cli.py` (added task)

```python
@dataclass
class TopicConfig:   # slug, name, brief, active
@dataclass
class SourceConfig:  # name, type, url, active, topics: list[str]

def load_topics(path: str = "config/topics.yaml") -> list[TopicConfig]
def load_sources(path: str = "config/sources.yaml") -> list[SourceConfig]
def sync_config(conn: sqlite3.Connection, topics: list[TopicConfig], sources: list[SourceConfig]) -> None
```

- `sync_config`: upsert topics by slug and sources by URL (name for URL-less inbox sources); rebuild `topic_sources` links; rows present in DB but absent from YAML are set `active=0` (never deleted). Idempotent — running twice changes nothing. Updates definition columns only; never touches `last_fetched_at`, `fetch_error_count`, `quality_score`.
- CLI (typer): `analyst topic add SLUG --name --brief` and `analyst source add --topic SLUG --type rss --url URL --name NAME` append to the YAML files and call `sync_config`. Programmatic YAML rewrite drops hand-written comments — accepted for v1, noted in `docs/commands.md`.
- The example placeholder entries in both YAML files are replaced by the real smoke-test topic/sources (see Verification).

---

## Error Handling Summary

| Failure | Behavior |
|---|---|
| Feed HTTP error / timeout / unparseable | `fetch_error_count += 1`; deactivate source at 5; other sources unaffected |
| Article extraction failure | Fall back to feed summary; no error count |
| Duplicate `content_hash` | Silent skip (Invariant 8) |
| Triage JSON parse failure | One retry with error feedback; then leave chunk untriaged and continue |
| 8th active thesis | `ValueError` (existing, gains regression test) |
| FTS query syntax from arbitrary text | Term quoting prevents it |

## Testing

**Unit (mocked HTTP + LLM, in-memory SQLite):**

- theses: stale boundary (29/30/31 days), `COALESCE` fallback to `created_at`, fragment rendering incl. empty case
- memory regression: 8th thesis raises; revision writes audit row
- rss: since-last-fetch filtering, first-fetch takes all, dedupe silent skip, summary fallback, error counting + deactivation at 5, counter reset on success
- triage: chunking at 20, score thresholds (0.19 skipped / 0.2 kept), parse-retry then graceful give-up, DB writes
- search: relevance ranking, recency boost ordering, k limits, topic isolation, exclude_ids, quote sanitization with hostile input
- config: sync idempotence, deactivation of removed rows, runtime columns untouched, CLI append+sync

**Smoke (`pytest -m smoke`, excluded by default, real network + API):**

- Scratch DB; topic "AI frontier labs" with 2–3 real feeds: arXiv cs.AI (`https://rss.arxiv.org/rss/cs.AI`), Simon Willison (`https://simonwillison.net/atom/everything/`), plus a third lab/news feed verified reachable at implementation time
- Full pipeline: sync_config → fetch_rss → triage_items → one real analyst run with related-context blocks present
- Assertions: items inserted, triage scores written, report section + memory writes produced
- Run once before the PR; cost ≈ cents (triage on deepseek-flash) + one analyst call

## Out of Scope (this sub-project)

- Report assembly, digest, Telegram, `daily_run.py` orchestration → Phase 3 spec
- Web UI → its own spec after Phase 3
- Embeddings/sqlite-vec, weekly compaction, source quality metrics → later phases per SPEC
