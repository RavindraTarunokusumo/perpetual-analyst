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
   │ retrieval/          │  FTS5 keyword search
   │  search.py          │  optional: embeddings.py (sqlite-vec) if FTS insufficient
   └─────────────────────┘
```

## Data Flow

```
sources → fetch → extract/dedupe → items
       → triage (Haiku: relevance score + 2-line summary per item)
       → analyst run (Opus: reasoning over triaged items + memory context)
       → TopicAnalysis (report section + memory writes)
       → memory writes (observations, thesis updates, dossier edit)
       → report assembly (multi-topic merge + exec summary)
       → Telegram (HTML digest ≤3,000 chars + .md file attachment)
```

The triage step exists to protect the analyst's context: the expensive model sees 10–30 distilled items per topic, not 200 raw articles.

## Entry Points

- `daily_run.py` — main orchestrator; called by cron/Task Scheduler as `python -m perpetual_analyst.daily_run`
- `cli.py` — typer CLI app, installed as `analyst` script; `analyst topic add`, `analyst source add`, `analyst run --topic x --dry-run`

## Module Boundaries

### `analyst/` ★ — The Product

The only module that calls the Anthropic API for reasoning (except `triage.py` which calls Haiku for classification).

| File | Responsibility |
|---|---|
| `agent.py` | `make_client() -> openai.OpenAI` (OpenRouter); `assemble_context(topic, items, conn, prompt, settings) -> list[dict]`; `run_topic(topic, items, conn, client, settings, dry_run=False) -> TopicAnalysis \| None` — calls `client.beta.chat.completions.parse()`, persists memory writes transactionally |
| `memory.py` | CRUD for dossier/observations/theses; `build_memory_context(topic_id, conn, token_budget=3000)` returning char-budget-truncated prompt text; `apply_all_memory_writes(topic_id, result, conn)` atomic bundle |
| `theses.py` | `get_stale_theses(topic_id, conn, days=30)` — single SQL query with `coalesce(updated_at, created_at)` comparison; `render_thesis_fragment(topic_id, conn)` — `is_stale` computed in DB, returns markdown list with `(stale)` markers |
| `triage.py` | `triage_items(items, topic_brief, client, settings, conn)` — Haiku batch call scoring items 0–1; items with score < 0.2 marked `status='skipped'` and filtered out; **does NOT call `conn.commit()`** — caller owns the transaction; graceful degradation (returns all items unchanged on API failure) |
| `schemas.py` | Pydantic output models: `TopicAnalysis`, `NewObservation`, `ThesisUpdate` |
| `prompts/analyst_system.md` | Finalized 12-rule system prompt with context template and JSON output schema |
| `prompts/weekly_review.md` | Self-review / memory compaction prompt |
| `prompts/digest.md` | Telegram digest generation prompt |

**Context assembly order (caching-friendly, stable first, volatile last):**

```
system prompt → topic brief → dossier → active theses (+ last update each)
→ last 7 days digest lines → yesterday's topic section
→ active observations (importance-sorted, budgeted)
→ today's triaged items with related-prior-context attached
```

### `ingestion/`

| File | Responsibility |
|---|---|
| `base.py` | `Fetcher` protocol / abstract base |
| `rss.py` | `fetch_rss(source, conn)` — feedparser + trafilatura; datetime-correct since-filter (both sides parsed as UTC-naive, not string compare); increments `fetch_error_count` and deactivates source at ≥5 errors |
| `inbox.py` | `scan_inbox(topic_slug, topic_id, source_id, conn)` — scan `inbox/<topic-slug>/` for .md/.txt/.pdf; pypdf extraction; hash-dedupe; moves processed files to `.processed/`. `get_or_create_inbox_source(conn, topic_id, topic_slug) -> int` — canonical shared helper; used by both CLI and `daily_run` |
| `extract.py` | trafilatura article text extraction helpers |

### `retrieval/`

| File | Responsibility |
|---|---|
| `search.py` | `related_observations(text, topic_id, conn, k=5)` and `related_items(text, topic_id, conn, k=3)` via FTS5; recency-boosted ordering (observations: last 30 days first; items: last 14 days first); gracefully returns `[]` on FTS parse error or empty text. **No vector search in V1.** |

### `store/`

| File | Responsibility |
|---|---|
| `db.py` | `init_db(path="data/analyst.db") -> sqlite3.Connection` — runs full DDL, FTS5 virtual tables (`items_fts`, `observations_fts`), and sync triggers; `insert_item(conn, source_id, content_hash, ...) -> bool` — only safe insertion path, enforces dedupe invariant |
| `models.py` | `@dataclass` row models with `from_row(cls, row)` classmethod: `User`, `Topic`, `Source`, `Item`, `Dossier`, `Thesis`, `ThesisUpdate`, `Observation`, `Report` |

### `report/`

| File | Responsibility |
|---|---|
| `assemble.py` | `assemble_report(topic_analyses, date, conn, client, settings, reports_dir)` — joins per-topic sections (calls `render_citations` per section), generates `digest_text` via OpenRouter, upserts `reports` row with `user_id=1`, writes `data/reports/brief-{date}.md`. Returns `report_id`. `digest_text` is HTML safely truncated to ≤3,000 chars with trailing unclosed tags stripped. |
| `render.py` | `render_citations(markdown, conn)` — batch IN query to look up all `[item:N]` tags; replaces inline with `[^N]` and appends footnotes section. Items not found in DB fall back to `(item N)`. |

### `delivery/`

| File | Responsibility |
|---|---|
| `telegram.py` | `send_report(report_id, conn)` — reads report row, sends `digest_text` as HTML message and `full_markdown` as `.md` file attachment, sets `delivered_at` on success; re-raises on error so caller can retry. `retry_undelivered(conn)` — retries reports where `delivered_at IS NULL` and `created_at < now - 1 hour`. Uses `python-telegram-bot` async via `asyncio.run`. Token/chat_id from `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` env vars; never logged. |

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
| Embeddings (future) | sqlite-vec + Voyage AI `voyage-3.5` — only if FTS proves insufficient |
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
