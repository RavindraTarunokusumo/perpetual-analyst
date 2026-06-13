# System Architecture

## Overview

One Python process, run on a schedule (cron / Windows Task Scheduler). Modules, not services.
The guiding rule: **the Analyst Agent is the product; everything else is plumbing.**

```
                ┌────────────────────────────────────────────┐
                │                daily_run.py                │
                └────────────────────────────────────────────┘
                      │              │                │
              1. ingest        2. analyze        3. deliver
                      │              │                │
   ┌──────────────────▼──┐   ┌───────▼────────┐   ┌───▼─────────────┐
   │ ingestion/          │   │ analyst/  ★    │   │ delivery/       │
   │  fetchers (rss,     │   │  agent.py      │   │  telegram.py    │
   │  file inbox, web)   │   │  memory.py     │   │  report_render  │
   │  extract.py         │   │  theses.py     │   └─────────────────┘
   │  dedupe.py          │   │  prompts/      │
   └─────────┬───────────┘   │  triage.py     │
             │               └───────┬────────┘
             ▼                       ▼
   ┌─────────────────────────────────────────────┐
   │ store/  — SQLite (sqlite3 + FTS5)           │
   │  items, chunks, topics, sources, theses,    │
   │  observations, dossiers, reports            │
   └─────────────────────────────────────────────┘
             ▲
   ┌─────────┴───────────┐
   │ retrieval/          │  FTS5 keyword search + BM25 recency boost
   │  search.py          │  optional: embeddings.py (sqlite-vec) only if FTS proves insufficient
   └─────────────────────┘
```

## Data Flow

```
sources → fetch → extract/dedupe → items (status: new)
       → triage (Haiku: relevance score + 2-line summary per item)
           score < 0.2 → status: skipped
           score ≥ 0.2 → analyst run (Opus: reasoning over triaged items + memory context)
       → TopicAnalysis (report section + memory writes)
       → memory writes (observations, thesis updates, dossier edit, items → analyzed) [one transaction]
       → report assembly (multi-topic merge + exec summary)
       → Telegram (HTML digest ≤3,000 chars + .md file attachment)
```

Item status lifecycle: `new` → (`skipped` by triage | remains `new`) → `analyzed` by `run_topic` (inside the memory-write transaction).

The triage step exists to protect the analyst's context: the expensive model sees 10–30 distilled items per topic, not 200 raw articles.

## Entry Points

- `daily_run.py` — main orchestrator; called by cron/Task Scheduler as `python -m perpetual_analyst.daily_run`
- `cli.py` — typer CLI app, installed as `analyst` script; `analyst topic add`, `analyst source add`, `analyst run --topic x --dry-run`

## Module Boundaries

### `analyst/` ★ — The Product

The only module that calls the Anthropic API for reasoning (except `triage.py` which calls Haiku for classification).

| File | Responsibility |
|---|---|
| `agent.py` | `make_client() -> openai.OpenAI` (OpenRouter); `assemble_context(topic, items, conn, prompt, settings) -> list[dict]` — includes stale-theses block and per-item related-context; `run_topic(topic, items, conn, client, settings, dry_run=False) -> TopicAnalysis \| None` — calls `client.beta.chat.completions.parse()`, reads result from `response.choices[0].message.parsed`, persists memory writes and marks items `analyzed` in one transaction |
| `memory.py` | CRUD for dossier/observations/theses; `build_memory_context(topic_id, conn, token_budget=3000)` returning char-budget-truncated prompt text; `apply_all_memory_writes(topic_id, result, conn)` atomic bundle |
| `theses.py` | Apply `ThesisUpdate`s (create/revise/retire); enforce ≤7 active; stale-flagging; render thesis fragment |
| `triage.py` | Triage model batch call — score (0–1) + 2-line summary per item; mark `status` on items |
| `schemas.py` | Pydantic output models: `TopicAnalysis`, `NewObservation`, `ThesisUpdate`; numeric fields use clamping validators (`@field_validator`) instead of `ge`/`le` bounds — provider structured-output schemas reject `minimum`/`maximum` JSON Schema keywords |
| `prompts/analyst_system.md` | Finalized 12-rule system prompt with context template and JSON output schema |
| `prompts/weekly_review.md` | Self-review / memory compaction prompt |
| `prompts/digest.md` | Telegram digest generation prompt |

**Context assembly order (caching-friendly, stable first, volatile last):**

```
system prompt → topic brief → dossier → active theses (+ last update each)
→ last 7 days digest lines → yesterday's topic section
→ active observations (importance-sorted, budgeted)
→ stale theses (≥30 days untouched — "revisit or retire" block)
→ today's triaged items, each with related prior context (top-5 obs + top-3 items via FTS5)
```

### `config.py`

`TopicConfig` / `SourceConfig` dataclasses; `load_topics(path)` / `load_sources(path)` (missing-file tolerant); `sync_config(conn, topics, sources)` — idempotent upsert. YAML is the source of truth for slug/name/brief/url; runtime columns (`last_fetched_at`, `fetch_error_count`) are DB-only. YAML-absent rows are deactivated; an empty list deactivates all of that kind. `inbox`-type sources are exempt from deactivation on absence.

### `ingestion/`

| File | Responsibility |
|---|---|
| `base.py` | `Fetcher` protocol / abstract base |
| `rss.py` | feedparser + trafilatura, since-last-fetch, error counting, writes `items` rows |
| `inbox.py` | Scan `inbox/<topic-slug>/` for .md/.txt/.pdf; pypdf extraction; hash-dedupe |
| `extract.py` | trafilatura article text extraction helpers |

### `retrieval/`

| File | Responsibility |
|---|---|
| `search.py` | `related_observations(text, topic_id, k, exclude_ids)` and `related_items(text, topic_id, k, exclude_ids)` — FTS5 BM25 with ×1.5 recency boost (30d obs / 14d items), term-quoting, topic isolation. No vector search. |

### `store/`

| File | Responsibility |
|---|---|
| `db.py` | `init_db(path="data/analyst.db") -> sqlite3.Connection` — runs full DDL, FTS5 virtual tables (`items_fts`, `observations_fts`), and sync triggers; `insert_item(conn, source_id, content_hash, ...) -> bool` — only safe insertion path, enforces dedupe invariant |
| `models.py` | `@dataclass` row models with `from_row(cls, row)` classmethod: `User`, `Topic`, `Source`, `Item`, `Dossier`, `Thesis`, `ThesisUpdate`, `Observation`, `Report` |

### `report/`

| File | Responsibility |
|---|---|
| `assemble.py` | `assemble_report(topic_results, conn, client, settings, report_date)` — builds SPEC §9 daily template (exec summary, per-topic sections with thesis fragments, open-questions/watch-next, citations); makes **one** daily `DigestOutput` structured call on the analyst model with a mechanical fallback on failure; `nothing_significant` topics get a one-liner. `persist_report(...)` INSERTs the `reports` row (UNIQUE on `report_date`; raises on duplicate) and writes `data/reports/brief-{date}.md` (DB row is authoritative; file is a regenerable copy). |
| `render.py` | `render_citations(markdown, conn)` — rewrites `[item:N]` tags to `[^k]` numbered footnotes in stable first-appearance order and appends a `## Sources reviewed` footnote list from `items`; unknown IDs render as plain text; `[obs:N]`/`[thesis:N]` pass through unchanged. |

### `delivery/`

| File | Responsibility |
|---|---|
| `telegram.py` | `send_report(report, conn)` — env-gated on `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`; sends HTML digest truncated at a paragraph boundary (`_balance_html` closes any open `<b>`/`<i>`) + full markdown as file attachment; stamps `delivered_at` on success; never raises — prints exception *type* only (secret hygiene). `retry_undelivered(conn)` sweeps `delivered_at IS NULL` rows. |

## Background Jobs

- **Daily run:** orchestrated by `daily_run.py` called by cron/Task Scheduler
- **Weekly compaction (Phase 4):** separate prompt + run; promotes observations → dossier; expires stale observations; flags untouched theses; writes self-review note to dossier

## External Integrations

| Service | Auth | Env var | Failure behavior |
|---|---|---|---|
| OpenRouter API | API key | `OPENROUTER_API_KEY` | Abort topic run; log error; continue other topics |
| Telegram Bot API | Bot token | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Store report; retry on next run (`delivered_at IS NULL` check) |

## Tech Stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| LLM API | OpenRouter via `openai.OpenAI(base_url="https://openrouter.ai/api/v1")` — not the Anthropic SDK |
| LLM (analyst) | `anthropic/claude-opus-4-8`, adaptive thinking via `extra_body={"thinking": {"type": "adaptive"}}`, structured output via `client.beta.chat.completions.parse()` |
| LLM (triage) | `deepseek/deepseek-v4-flash`, no thinking |
| Model config | `config/settings.yaml` → `Settings.analyst` / `Settings.triage` (`ModelConfig(id, thinking)`) |
| Storage | SQLite + FTS5, single file `data/analyst.db` |
| Embeddings | sqlite-vec + Voyage AI `voyage-3.5` — deferred; add only if FTS5 retrieval proves insufficient |
| Fetching | feedparser, httpx, trafilatura, pypdf |
| Telegram | python-telegram-bot (send-only V1) |
| Scheduling | OS cron / Windows Task Scheduler |
| Config | `config/settings.yaml`, `.env` |
| CLI | typer |

## Invariants

- **No services.** One process, one SQLite file.
- **One analyst call per topic per day.** See `AGENTS.md` invariants.
- **Prompt caching:** stable system prompt is always the first content block.
- **Error isolation:** one failing topic must not kill the daily run for other topics. Wrap each topic's analyst run in a try/except.
- **No vectors in V1.** Add sqlite-vec only when a concrete FTS retrieval failure is observed.
