# Changelog

Record notable behavior, architecture, API, persistence, or workflow changes.

## 2026-06-11 — Phase 4: memory & thesis maturity (compaction, thesis history, prompt caching)

Summary:

- What changed: New weekly compaction pipeline (`analyst/compaction.py`, `weekly_run.py`); thesis audit trail injected into daily prompt; prompt-caching stable-prefix ordering enforced on both daily and weekly model calls.
- Why: Phase 4 — close the observation lifecycle (expiry + promotion into dossier), surface thesis confidence history to the analyst, and reduce per-call token costs via prompt caching.
- User-visible impact:
  - `analyst weekly` / `python -m perpetual_analyst.weekly_run` now runs observation expiry + weekly review per active topic. Supports `--dry-run` and `--topic <slug>`.
  - Daily analyst prompt now includes a `## Thesis history` section showing confidence trajectory per active thesis.
  - Active theses untouched for >30 days are marked `(stale)` in the daily prompt.
- Architecture notes:
  - Two separate background cadences: daily (`daily_run.py`) and weekly (`weekly_run.py`). Weekly is one additional model call per topic per week — not per day.
  - `expire_observations` is pure SQL, no model call; commits separately; idempotent.
  - `apply_weekly_review` writes dossier rewrite + promoted observation IDs in one `with conn:` transaction. Weekly run never edits/retires theses.
  - `WeeklyReviewOutput` schema: `dossier_rewrite`, `promoted_observation_ids`, `notes` (<200-word self-review appended to dossier).
  - `agent.with_cache_control` helper attaches ephemeral `cache_control` breakpoint to the stable system prompt; applied on both `run_topic` and `run_weekly_review`.
  - `render_thesis_trail` (in `theses.py`) builds per-thesis confidence history from `thesis_updates` rows.
- Migration notes: No new tables. `observations.status` column already supported `promoted`/`expired` values from Phase 1 DDL.
- Related PR/commit: phase-4-compaction branch

## 2026-06-10 — Phase 2+3: CLI, ingestion, retrieval, report, delivery

Summary:

- What changed: Full pipeline implemented end-to-end. New modules: `cli.py` (typer CLI with `topic add/list`, `source add/list`, `run`, `report show`), `analyst/theses.py` (`get_stale_theses`, `render_thesis_fragment` with `is_stale` computed in DB), `analyst/triage.py` (`triage_items` — Haiku batch pass, no `conn.commit()`, caller owns transaction), `ingestion/rss.py` (`fetch_rss` — feedparser+trafilatura, UTC-naive datetime filter, error-count deactivation), `retrieval/search.py` (`related_observations` and `related_items` via FTS5, recency-boosted), `report/render.py` (`render_citations` — batch IN query, `[item:N]` → `[^N]` footnotes), `report/assemble.py` (`assemble_report` — digest via OpenRouter, upsert with `user_id=1`, writes `data/reports/brief-{date}.md`), `delivery/telegram.py` (`send_report` + `retry_undelivered` async via `asyncio.run`), `daily_run.py` (full orchestrator with per-topic try/except and isolated assemble+deliver block).
- Why: Phase 2 and Phase 3 — complete the pipeline from ingestion through delivery.
- User-visible impact: `analyst run` now ingests RSS feeds, triages items, runs analysis, assembles and delivers the daily report to Telegram. `analyst report show` reads stored reports from DB.
- Architecture notes:
  - `triage_items` does NOT call `conn.commit()` — caller owns the transaction.
  - `get_or_create_inbox_source` is the canonical shared helper in `ingestion/inbox.py`; not duplicated in CLI or `daily_run`.
  - `fetch_rss` datetime filter parses both sides as UTC-naive datetimes (not string compare).
  - `assemble_report` writes `user_id=1` — single-user MVP, not multi-user.
  - `digest_text` HTML is safely truncated to ≤3,000 chars with trailing unclosed tag stripped.
  - `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` come from env vars and are never logged.
  - `assemble_report` + `send_report` are wrapped in a single try/except in `daily_run` so Telegram failure leaves the report persisted for `retry_undelivered` on the next run.
- Migration notes: No schema changes from Phase 1. `reports` table was already defined; `user_id=1` is now consistently populated.
- Related PR/commit: phase-2-cli-and-ingestion branch

## 2026-06-10 — Phase 1: analyst prototype implementation

Summary:

- What changed: Core analyst pipeline implemented — `store/db.py` (full SQLite schema with FTS5 and sync triggers), `store/models.py` (dataclass row models), `config.py` (`Settings`/`ModelConfig`), `analyst/memory.py` (memory CRUD + `build_memory_context` + `apply_all_memory_writes`), `analyst/agent.py` (OpenRouter client, context assembly, `run_topic`), `ingestion/inbox.py` (inbox scanner with content_hash dedupe).
- Why: Phase 1 — functional analyst prototype that can read from a file inbox and call the LLM.
- User-visible impact: `analyst run --topic <slug> --dry-run` now prints assembled prompt. `analyst run --topic <slug>` calls OpenRouter and persists memory writes.
- Architecture note: All LLM calls go through OpenRouter (`openai.OpenAI(base_url="https://openrouter.ai/api/v1")`), not the Anthropic SDK. `OPENROUTER_API_KEY` is the required env var (replaces `ANTHROPIC_API_KEY`). Model IDs are configured in `config/settings.yaml`.
- Migration notes: N/A — first functional implementation.
- Related PR/commit: phase-1-analyst-prototype branch

## 2026-06-10 — Initial project setup

Summary:

- What changed: Repository scaffolded from SPEC.md. Harness, docs, source skeleton, and TODO created.
- Why: Phase 1 start — analyst prototype with manual inbox input.
- User-visible impact: None yet. No pipeline or LLM calls implemented.
- Migration notes: N/A — fresh project.
- Related PR/commit: initial commit
