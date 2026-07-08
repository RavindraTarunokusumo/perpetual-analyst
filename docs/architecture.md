# System Architecture

## Overview

One Python process, run on a schedule (cron / Windows Task Scheduler). Modules, not services.
The guiding rule: **the Analyst Agent is the product; everything else is plumbing.**

Daily memory and retrieval live on the **Nexus substrate** (Postgres + pgvector). PA keeps
SQLite for operational tables (topics, sources, items, reports, delivery) and for the
**weekly discovery/compaction subsystem** (legacy dossier/theses/observations in SQLite).

```
                ┌────────────────────────────────────────────┐
                │                daily_run.py                │
                └────────────────────────────────────────────┘
                      │              │                │
              1. ingest        2. synthesize     3. deliver
                      │              │                │
   ┌──────────────────▼──┐   ┌───────▼────────┐   ┌───▼─────────────┐
   │ ingestion/          │   │ substrate.py ★ │   │ delivery/       │
   │  fetchers (rss,     │   │ Nexus boundary │   │  telegram.py    │
   │  file inbox, web)   │   │ ingest/retrieve│   └─────────────────┘
   │  extract.py         │   │ synthesize/    │   ┌─────────────────┐
   │  dedupe.py          │   │ persist_bundle │   │ report/assemble   │
   └─────────┬───────────┘   └───────┬────────┘   └─────────────────┘
             │                       │
   ┌─────────▼───────────┐           ▼
   │ analyst/            │   ┌───────────────────────────────┐
   │  synthesis.py ★     │   │ Postgres (Nexus submodule)    │
   │  triage.py          │   │ documents/spans (pgvector)    │
   │  compaction.py      │   │ + 8 analytical tables         │
   │  discovery.py       │   └───────────────────────────────┘
   └─────────┬───────────┘
             │
   ┌─────────▼───────────┐      ┌──────────────────┐
   │ store/ — SQLite ops │      │ quality.py        │
   │ topics, sources,    │      │  per-source       │
   │ items, reports, ... │      │  quality scoring  │
   └─────────────────────┘      └──────────────────┘
```

`substrate.py` is the **only** PA module that imports Nexus (`app.*`) or connects to Postgres.
No other module touches the memory corpus or analytical tables directly.

## Data Flow

```
sources → fetch → extract/dedupe → items (SQLite)
       → triage (Qwen flash: relevance score + 2-line summary per item)
       → substrate.ingest (zero-LLM: sentence-split + local embed → Postgres corpus, topic-scoped)
       → synthesis.run_daily_for_topic (one qwen3.7-max call per topic per day)
           → substrate.retrieve (sentence-window, window=2, top_k=15, fetch_k=60)
           → substrate.synthesize → NarrativeUpdate bundle
           → substrate.persist_bundle (transactional Postgres write)
       → assemble_report (join per-topic NarrativeUpdate.briefing_markdown)
       → Telegram (HTML digest ≤3,000 chars + .md file attachment)

Cross-session (on demand, no extra daily analyst call):
       → substrate.answer (grounded Q&A over topic corpus + analytical objects)
       → substrate.resolve_lifecycle via `analyst score` (prediction expiry + claim decay)

Weekly additions (weekly_run.py):
       → expire_observations + run_weekly_review (SQLite dossier/observations — legacy weekly path)
       → discover_sources (per topic, web search via OpenRouter or Perplexity)
           → source_candidates rows (status='pending'; human reviews in Web UI)
       → compute_source_quality: triage hit-rate + citation rate + uniqueness + freshness lead
       → bottom_decile: log worst-scoring sources (no auto-removal)
       → transition_probation: promote past-probation sources to 'active'
```

The triage step exists to protect the analyst's context: the expensive model sees 10–30 distilled items per topic, not 200 raw articles. Corpus ingest is deterministic (no LLM); the single daily analyst call is the synthesis step.

## Entry Points

- `daily_run.py` — main orchestrator; called by cron/Task Scheduler as `python -m perpetual_analyst.daily_run`
- `weekly_run.py` — weekly compaction orchestrator; `python -m perpetual_analyst.weekly_run [--dry-run] [--topic <slug>]`
- `cli.py` — typer CLI app, installed as `analyst` script; `analyst topic add`, `analyst source add`, `analyst run` (delegates to `daily_run`), `analyst ask`, `analyst score`, `analyst weekly [--dry-run] [--topic <slug>]`

## Module Boundaries

### `substrate.py` ★ — Nexus Boundary

Single async boundary between PA and the Nexus memory substrate. Loads secrets from `Nexus/.env`
(`DATABASE_URL`, `QWEN_CLOUD_API_KEY`, `LLM_BASE_URL`). Public interface:

| Function | Responsibility |
|---|---|
| `ingest(scope, title, url, text, published_at)` | Persist document + dedupe + sentence-span embed (BAAI/bge-small-en-v1.5, 384-dim); returns `document_id` or `None` on duplicate |
| `retrieve(scope, query, k)` | Topic-scoped sentence-window retrieval (pgvector ANN + optional hybrid) |
| `synthesize(topic_id, scope, focus, k)` | One structured synthesis call (qwen3.7-max) → `NarrativeUpdate` |
| `persist_bundle(topic_id, bundle, ctx)` | Transactional write of claims, events, narrative version, hypotheses, predictions, source_profiles |
| `answer(scope, question, k)` | Cross-session grounded Q&A via Nexus Chain-of-Note reader |
| `resolve_lifecycle(stale_after_days, scope)` | Expire overdue predictions; mark aged claims `stale` |
| `get_or_create_watch_topic(slug, name, ...)` | Mirror PA topic slug → Postgres `watch_topics` row |

### `analyst/` ★ — The Product

Daily reasoning flows through `synthesis.py` → `substrate.py`. Weekly compaction and discovery
still use `compaction.py`, `memory.py`, and `discovery.py` against SQLite.

| File | Responsibility |
|---|---|
| `synthesis.py` | `run_daily_for_topic(slug, name, brief, item_titles)` — builds retrieval focus, calls `substrate.synthesize` + `substrate.persist_bundle`; the daily analyst entry point |
| `triage.py` | `triage_items(items, topic_brief, client, settings, conn)` — Qwen flash batch call scoring items 0–1; items with score < 0.2 marked `status='skipped'` and filtered out; **does NOT call `conn.commit()`** — caller owns the transaction; graceful degradation (returns all items unchanged on API failure) |
| `schemas.py` | Pydantic output models: `NarrativeUpdate` (daily), `WeeklyReviewOutput`, `DiscoveryOutput`, `DiscoveryCandidate` |
| `agent.py` | `make_client(provider)` — Qwen (DashScope-intl) for daily/triage; OpenRouter/Perplexity for optional discovery; `with_cache_control()` for weekly review prompt caching |
| `memory.py` | CRUD for SQLite dossier/observations/theses — used by **weekly compaction only** |
| `theses.py` | `get_stale_theses`, `render_thesis_fragment`, `render_thesis_trail` — weekly context helpers |
| `compaction.py` | `expire_observations(topic_id, conn)` — pure SQL; `run_weekly_review(...)` — weekly model call; `apply_weekly_review(...)` — transactional SQLite write |
| `candidates.py` | Operator approval workflow for `source_candidates`: validates and fetches only public HTTP(S) URLs, creates probation sources, links topic/source rows, and marks candidates approved/rejected. No model calls. |
| `discovery.py` | `discover_sources(topic, conn, client, settings)` — weekly per-topic model call; proposes 3–5 new source candidates stored in `source_candidates` with `status='pending'`. Provider isolated behind `web_search_extra(provider)` and `make_client(provider=...)`. |
| `prompts/digest.md` | Telegram digest generation prompt |
| `prompts/weekly_review.md` | Self-review / memory compaction prompt (SQLite weekly path) |
| `prompts/discovery.md` | Source discovery prompt |

**Daily synthesis context assembly (in `substrate.synthesize`):**

```
[retrieved — sentence-window passages, topic-scoped, budgeted by top_k]
→ current narrative_states version (source of truth)
→ active claims (topic_id + status=active, recency-bounded)
→ active hypotheses (≤7)
→ open predictions
→ today's new source passages (from retrieve)
→ JSON schema for NarrativeUpdate
```

`narrative_states` is the source of truth; the SQLite dossier (weekly path) is a separate legacy projection.

### `ingestion/`

| File | Responsibility |
|---|---|
| `base.py` | `Fetcher` protocol / abstract base |
| `rss.py` | `fetch_rss(source, conn)` — feedparser + trafilatura; datetime-correct since-filter (both sides parsed as UTC-naive, not string compare); increments `fetch_error_count` and deactivates source at ≥5 errors |
| `inbox.py` | `scan_inbox(topic_slug, topic_id, source_id, conn)` — scan `inbox/<topic-slug>/` for .md/.txt/.pdf; pypdf extraction; hash-dedupe; moves processed files to `.processed/`. `get_or_create_inbox_source(conn, topic_id, topic_slug) -> int` — canonical shared helper; used by both CLI and `daily_run` |
| `extract.py` | trafilatura article text extraction helpers |

### `store/`

| File | Responsibility |
|---|---|
| `db.py` | `init_db(path="data/analyst.db") -> sqlite3.Connection` — runs SQLite DDL for operational tables; `insert_item(conn, source_id, content_hash, ...) -> bool` — only safe insertion path, enforces dedupe invariant |
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
| `assemble.py` | `assemble_report(briefings, date, conn, client, settings, reports_dir)` — joins per-topic `NarrativeUpdate.briefing_markdown` sections (or "Nothing significant." when `nothing_significant`), generates `digest_text` via Qwen, upserts `reports` row with `user_id=1`, writes `data/reports/brief-{date}.md`. Returns `report_id`. Provenance lives in Postgres `claim_evidence`, not inline `[item:N]` tags. |

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

- **Daily run:** orchestrated by `daily_run.py`; one synthesis call (`qwen3.7-max`) per active topic. Triage is a separate Qwen flash function call (not counted as the analyst call). Report assembly joins `briefing_markdown` from each topic's `NarrativeUpdate`.
- **Lifecycle scoring:** `analyst score` (or cron) calls `substrate.resolve_lifecycle` — expires overdue predictions and marks aged claims `stale`; no extra analyst call.
- **Weekly compaction:** orchestrated by `weekly_run.py`; one model call per active topic for SQLite dossier rewrite (distinct cadence from the daily run). Steps per topic: (1) `expire_observations` — pure SQL; (2) `run_weekly_review` — model call over SQLite dossier + observations + theses; (3) `apply_weekly_review` — transactional SQLite write. The weekly run does **not** edit daily Postgres hypotheses. After the compaction loop: (4) `discover_sources`; (5) `compute_source_quality` + log `bottom_decile`; (6) `transition_probation`. Steps 5–6 are deterministic and run regardless of `--dry-run`; only model calls (steps 2 and 4) are gated by `--dry-run`.

## External Integrations

| Service | Auth | Env var | Failure behavior |
|---|---|---|---|
| Qwen Cloud (DashScope-intl) | API key | `QWEN_CLOUD_API_KEY` (in `Nexus/.env`) | Abort topic run; log error; continue other topics |
| Postgres (Nexus) | Connection string | `DATABASE_URL` (in `Nexus/.env`) | Abort topic run; log error; continue other topics |
| Telegram Bot API | Bot token | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Store report; retry on next run (`delivered_at IS NULL` check) |
| Web search (discovery) | OpenRouter web plugin or Perplexity | `OPENROUTER_API_KEY` or `PERPLEXITY_API_KEY` | Skip discovery for that topic; log error; continue. Provider isolated behind `web_search_extra(provider)` in `analyst/discovery.py`. |

## Tech Stack

| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| LLM API (daily) | Qwen Cloud via DashScope-intl OpenAI-compatible endpoint (`openai.OpenAI`) |
| LLM (triage) | `qwen3.6-flash` — plain function, no thinking |
| LLM (synthesis) | `qwen3.7-max` — structured JSON via Nexus `LLMClient.complete_json()` |
| LLM (digest) | `qwen3.7-plus` via `settings.analyst.id` |
| Embeddings | Local **BAAI/bge-small-en-v1.5** @384-dim via Nexus `Embedder` (sentence-transformers) |
| Retrieval | Nexus sentence-window (pgvector ANN); topic-scoped via `Document.scope` |
| Operational storage | SQLite, single file `data/analyst.db` |
| Memory storage | Postgres (Nexus submodule), Alembic migrations in `Nexus/app/db/migrations/` |
| Nexus dependency | Git submodule at `Nexus/`, `pip install -e ./Nexus` |
| Fetching | feedparser, httpx, trafilatura, pypdf |
| Telegram | python-telegram-bot (send-only V1) |
| Web dashboard | Flask + Jinja2, `markdown` for report rendering |
| Scheduling | OS cron / Windows Task Scheduler |
| Config | `config/settings.yaml`, `.env`, `Nexus/.env` |
| CLI | typer |

## Invariants

- **No services.** One process; two databases (SQLite ops + Postgres memory).
- **One analyst call per topic per day.** The synthesis call (`substrate.synthesize`). Triage is a function, not an agent. See `AGENTS.md` invariants.
- **Nexus boundary.** Only `substrate.py` imports `app.*` or connects to Postgres.
- **Error isolation:** one failing topic must not kill the daily run for other topics. Wrap each topic's synthesis run in a try/except.
- **Transactional bundle writes.** `persist_bundle` commits all analytical objects together or rolls back (Postgres transaction).