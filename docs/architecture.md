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
             │               │  discovery.py  │
             ▼               └───────┬────────┘
   ┌─────────────────────────────────────────────┐
   │ store/  — SQLite (sqlite3 + FTS5)           │
   │  items, chunks, topics, sources, theses,    │
   │  observations, dossiers, reports,           │
   │  citations, source_candidates               │
   └─────────────────────────────────────────────┘
             ▲
   ┌─────────┴───────────┐      ┌──────────────────┐
   │ retrieval/          │      │ quality.py        │
   │  search.py          │      │  per-source       │
   │  FTS5 keyword search│      │  quality scoring  │
   └─────────────────────┘      └──────────────────┘
```

## Data Flow

```
sources → fetch → extract/dedupe → items
       → triage (Haiku: relevance score + 2-line summary per item)
       → analyst run (Opus: reasoning over triaged items + memory context)
       → TopicAnalysis (report section + memory writes)
       → memory writes (observations, thesis updates, dossier edit)
       → report assembly (multi-topic merge + exec summary)
           → _record_citations: [item:N] tags → citations table (idempotent)
       → Telegram (HTML digest ≤3,000 chars + .md file attachment)

Weekly additions (weekly_run.py):
       → discover_sources (per topic, web search via OpenRouter)
           → source_candidates rows (status='pending'; human reviews in Web UI)
       → compute_source_quality: triage hit-rate + citation rate + uniqueness + freshness lead
       → bottom_decile: log worst-scoring sources (no auto-removal)
       → transition_probation: promote past-probation sources to 'active'
```

The triage step exists to protect the analyst's context: the expensive model sees 10–30 distilled items per topic, not 200 raw articles.

## Entry Points

- `daily_run.py` — main orchestrator; called by cron/Task Scheduler as `python -m perpetual_analyst.daily_run`
- `weekly_run.py` — weekly compaction orchestrator; `python -m perpetual_analyst.weekly_run [--dry-run] [--topic <slug>]`
- `cli.py` — typer CLI app, installed as `analyst` script; `analyst topic add`, `analyst source add`, `analyst run --topic x --dry-run`, `analyst weekly [--dry-run] [--topic <slug>]`

## Module Boundaries

### `analyst/` ★ — The Product

The only module that calls the Anthropic API for reasoning (except `triage.py` which calls Haiku for classification).

| File | Responsibility |
|---|---|
| `agent.py` | `make_client() -> openai.OpenAI` (OpenRouter); `assemble_context(topic, items, conn, prompt, settings) -> list[dict]`; `run_topic(topic, items, conn, client, settings, dry_run=False) -> TopicAnalysis \| None` — calls `client.beta.chat.completions.parse()`, persists memory writes transactionally |
| `memory.py` | CRUD for dossier/observations/theses; `build_memory_context(topic_id, conn, token_budget=3000)` returning char-budget-truncated prompt text; `apply_all_memory_writes(topic_id, result, conn)` atomic bundle |
| `theses.py` | `get_stale_theses(topic_id, conn, days=30)` — single SQL query with `coalesce(updated_at, created_at)` comparison; `render_thesis_fragment(topic_id, conn)` — `is_stale` computed in DB, returns markdown list with `(stale)` markers; `render_thesis_trail(topic_id, conn)` — per-thesis confidence history from `thesis_updates` rendered as `confidence 0.60→0.80 over N update(s)` |
| `compaction.py` | `expire_observations(topic_id, conn)` — pure SQL, no model call; sets `status='expired'` for importance-1 observations older than 30 days and importance-2 older than 90 days; `run_weekly_review(topic, conn, client, settings, dry_run=False)` — single weekly model call returning `WeeklyReviewOutput`; `apply_weekly_review(topic_id, result, conn)` — transactional write: dossier rewrite + promoted observation IDs + appends <200-word self-review note to dossier |
| `triage.py` | `triage_items(items, topic_brief, client, settings, conn)` — Haiku batch call scoring items 0–1; items with score < 0.2 marked `status='skipped'` and filtered out; **does NOT call `conn.commit()`** — caller owns the transaction; graceful degradation (returns all items unchanged on API failure) |
| `schemas.py` | Pydantic output models: `TopicAnalysis`, `NewObservation`, `ThesisUpdate`, `WeeklyReviewOutput` (fields: `dossier_rewrite`, `promoted_observation_ids`, `notes`); Phase 5: `DiscoveryOutput`, `DiscoveryCandidate` |
| `candidates.py` | Operator approval workflow for `source_candidates`: validates and fetches only public HTTP(S) URLs, creates probation sources, links topic/source rows, and marks candidates approved/rejected. No model calls. |
| `discovery.py` | `discover_sources(topic, conn, client, settings)` — weekly per-topic model call through the configured discovery provider; proposes 3–5 new source candidates stored in `source_candidates` with `status='pending'`. `mine_outbound_domains(topic_id, conn)` ranks domains already supplying cited material as context for the prompt. Provider isolated behind `web_search_extra(provider)` and `make_client(provider=...)`. |
| `prompts/analyst_system.md` | Finalized 12-rule system prompt with context template and JSON output schema |
| `prompts/weekly_review.md` | Self-review / memory compaction prompt |
| `prompts/digest.md` | Telegram digest generation prompt |
| `prompts/discovery.md` | Source discovery prompt — instructs the model to propose new candidate sources given cited domain context |

**Context assembly order (caching-friendly, stable first, volatile last):**

```
[stable — cache breakpoint after system prompt]
system prompt → topic brief → dossier → active theses (+ last update each)
→ thesis history (confidence trajectory per thesis from thesis_updates)

[volatile]
→ last 7 days digest lines → yesterday's topic section
→ active observations (importance-sorted, budgeted)
→ today's triaged items with related-prior-context attached
```

`assemble_context` attaches an ephemeral `cache_control` breakpoint (via `agent.with_cache_control`) to the stable system prompt; the same helper is used on both the daily (`run_topic`) and weekly (`run_weekly_review`) model calls.

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
| `db.py` | `init_db(path="data/analyst.db") -> sqlite3.Connection` — runs full DDL, FTS5 virtual tables (`items_fts`, `observations_fts`), and sync triggers; `insert_item(conn, source_id, content_hash, ...) -> bool` — only safe insertion path, enforces dedupe invariant. Phase 5: also creates `citations` and `source_candidates` tables; adds `sources.status` and `sources.probation_until` columns via `_ensure_columns()` (idempotent, guarded by `PRAGMA table_info`). |
| `models.py` | `@dataclass` row models with `from_row(cls, row)` classmethod: `User`, `Topic`, `Source`, `Item`, `Dossier`, `Thesis`, `ThesisUpdate`, `Observation`, `Report` |

### `quality.py`

Top-level module (not inside `analyst/`).

| Function | Responsibility |
|---|---|
| `compute_source_quality(conn)` | For each source with ≥1 item: computes triage hit-rate, citation rate, uniqueness rate (only cited source in a report group), and freshness-lead rate (earliest published cited item in a report group); writes `sources.quality_score = 0.35*hit + 0.35*citation + 0.15*uniqueness + 0.15*freshness`. Deterministic SQL/Python + UPDATE, no model call. |
| `bottom_decile(conn)` | Returns worst-scoring sources (≥ `min_items`, probation excluded) as drop candidates for operator review. Does not remove anything. |
| `transition_probation(conn)` | Promotes sources whose `probation_until` date has passed to `status='active'`. Pure SQL. |

### `report/`

| File | Responsibility |
|---|---|
| `assemble.py` | `assemble_report(topic_analyses, date, conn, client, settings, reports_dir)` — joins per-topic sections (calls `render_citations` per section), generates `digest_text` via OpenRouter, upserts `reports` row with `user_id=1`, writes `data/reports/brief-{date}.md`. Returns `report_id`. `digest_text` is HTML safely truncated to ≤3,000 chars with trailing unclosed tags stripped. `_record_citations(report_id, report_date, markdown, conn)` resolves `[item:N]` tags to their source and inserts rows into `citations` (idempotent via INSERT OR IGNORE). |
| `render.py` | `render_citations(markdown, conn)` — batch IN query to look up all `[item:N]` tags; replaces inline with `[^N]` and appends footnotes section. Items not found in DB fall back to `(item N)`. `cited_item_ids(markdown)` extracts the set of item IDs referenced in a rendered markdown string. |

### `web.py`

Local operator UI served by `analyst web` using the Python standard library. It
renders pending source candidates, approval/dismissal forms, source probation
state, quality scores, and bottom-decile markers. Approval delegates to
`analyst/candidates.py`, which validates URLs before fetch and never logs
secrets.

### `delivery/`

| File | Responsibility |
|---|---|
| `telegram.py` | `send_report(report_id, conn)` — reads report row, sends `digest_text` as HTML message and `full_markdown` as `.md` file attachment, sets `delivered_at` on success; re-raises on error so caller can retry. `retry_undelivered(conn)` — retries reports where `delivered_at IS NULL` and `created_at < now - 1 hour`. Uses `python-telegram-bot` async via `asyncio.run`. Token/chat_id from `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` env vars; never logged. |

## Background Jobs

- **Daily run:** orchestrated by `daily_run.py`; one analyst model call per active topic. After report assembly, `_record_citations` records every cited `[item:N]` tag into the `citations` table (idempotent).
- **Weekly compaction:** orchestrated by `weekly_run.py`; one model call per active topic (distinct cadence from the daily run, not an additional daily call). Steps per topic: (1) `expire_observations` — pure SQL, no model, marks importance-1/>30d and importance-2/>90d observations `expired`; (2) `run_weekly_review` — model call over dossier + active observations + active theses, returns `WeeklyReviewOutput`; (3) `apply_weekly_review` — rewrites dossier, marks promoted observations `status='promoted'`, appends self-review note. The weekly run does **not** edit or retire theses — that remains exclusively in the daily run to preserve the audit-trail invariant. After the compaction loop: (4) `discover_sources` — per-topic model call proposing new source candidates (stored as `source_candidates` with `status='pending'`; no auto-add); (5) `compute_source_quality` + log `bottom_decile` drop candidates; (6) `transition_probation` — promotes past-probation sources. Steps 5–6 are deterministic and run regardless of `--dry-run`; only model calls (steps 2 and 4) are gated by `--dry-run`. Source candidate approval is local operator action through `analyst web`.

## External Integrations

| Service | Auth | Env var | Failure behavior |
|---|---|---|---|
| OpenRouter API | API key | `OPENROUTER_API_KEY` | Abort topic run; log error; continue other topics |
| Telegram Bot API | Bot token | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Store report; retry on next run (`delivered_at IS NULL` check) |
| Web search (discovery) | OpenRouter web plugin or Perplexity | `OPENROUTER_API_KEY` or `PERPLEXITY_API_KEY` | Skip discovery for that topic; log error; continue. Provider isolated behind `web_search_extra(provider)` in `analyst/discovery.py` and `make_client(provider=...)` in `analyst/agent.py`. |

## Tech Stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| LLM API | OpenRouter via `openai.OpenAI(base_url="https://openrouter.ai/api/v1")` — not the Anthropic SDK |
| LLM (analyst) | `anthropic/claude-opus-4-8`, adaptive thinking via `extra_body={"thinking": {"type": "adaptive"}}`, structured output via `client.beta.chat.completions.parse()` |
| LLM (triage) | `deepseek/deepseek-v4-flash`, no thinking |
| Model config | `config/settings.yaml` → `Settings.analyst` / `Settings.triage` (`ModelConfig(id, thinking)`) |
| Storage | SQLite + FTS5, single file `data/analyst.db` |
| Embeddings (optional) | sqlite-vec + Voyage AI `voyage-3.5`; disabled by default and gated on recorded FTS insufficiency |
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
