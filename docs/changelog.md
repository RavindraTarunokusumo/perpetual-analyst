# Changelog

Record notable behavior, architecture, API, persistence, or workflow changes.

## 2026-06-14 — Web UI: local dashboard (out of SPEC v1)

Summary:

- What changed: New package `src/perpetual_analyst/web/` — `app.py` (Flask factory `create_app(db_path)` with all routes and a `before_request` Origin-check CSRF guard), `queries.py` (read-only view-model builders for all dashboard pages), `actions.py` (3 write actions + run lock/thread/status). New `analyst web` CLI command (binds `127.0.0.1:8080` by default; `--host/--port/--db-path` options). New deps: `flask`, `markdown`.
- Behavior: 8 read pages (Today, Topics, Topic detail, Thesis history, Reports, Report detail, Items, Ops, Reading mode). 3 write actions reuse existing guarded paths: `add_inbox_item` → `store.db.insert_item` (silent content-hash dedupe); `retry_all` → `delivery.telegram.retry_undelivered` (disabled when Telegram env unset); `trigger_run` → `daily_run.run_daily` in a daemon thread guarded by `threading.Lock` (single active run enforced). Reading mode is cookie-backed (`SameSite=Lax, httponly`); `/` redirects to `/reading` when set. Report markdown is rendered with `|safe` (analyst-controlled local source; loopback-only tool). Action errors surface `type(exc).__name__` only (Invariant 7 preserved).
- User-visible impact: `analyst web` opens a browser-accessible local dashboard at `http://127.0.0.1:8080`. No new CLI commands beyond `analyst web`.
- Architecture note: No schema changes — the web layer reads existing tables. `queries.py` contains all dashboard SELECTs; no bare SQL in routes. The Origin check is the CSRF guard for the no-auth loopback tool.
- Migration notes: `pip install -e .` (or `uv pip install -e .`) to pull in `flask` and `markdown`.
- Related PR/commit: web-ui-dashboard branch

## 2026-06-13 — Phase 3: automated delivery

Summary:

- What changed: `report/render.py` (`render_citations` — `[item:N]` → `[^k]` numbered footnotes, stable first-appearance order, `## Sources reviewed` list; unknown IDs pass through as plain text), `report/assemble.py` (`assemble_report` + `persist_report` — SPEC §9 daily template, one daily `DigestOutput` call with mechanical fallback, `nothing_significant` one-liner, `reports` row UNIQUE on `report_date`), `analyst/schemas.py` (`DigestOutput {executive_summary, digest_text}` — no `ge`/`le` bounds), `analyst/prompts/digest.md` (finalized digest voice rules), `delivery/telegram.py` (`send_report` env-gated, HTML truncated at paragraph boundary with `_balance_html`, secret hygiene; `retry_undelivered` sweeps `delivered_at IS NULL`), `daily_run.py` (full orchestrator: sync → ingest → triage → analyze → assemble → deliver, per-topic and per-stage isolation, `dry_run` skips all API/delivery, `force_utf8_stdout` for Windows cp1252), `cli.py` (`analyst run` wired to `run_daily`), `analyst/triage.py` (`select_analyst_items` — topic-scoped, `status='new' AND triage_score >= SKIP_THRESHOLD`, best-first), `config.py` (`sync_config` resets `fetch_error_count = 0` on source reactivation), `analyst/agent.py` (`run_topic` short-circuits empty items — no LLM call when nothing to analyze).
- Behavior: Complete end-to-end pipeline from cron/Task Scheduler to Telegram delivery. Item status lifecycle (`new` → `skipped` | `analyzed`) is fully exercised. A second run on the same day skips analysis and only retries delivery. Failed Telegram sends are retried on the next run.
- User-visible impact: `analyst run` (and `python -m perpetual_analyst.daily_run`) now executes the full pipeline. `--dry-run` skips all API calls and delivery. Daily report is stored in `reports` table and written to `data/reports/brief-{date}.md`; HTML digest is sent to Telegram.
- Architecture note: `assemble_report` makes one additional `DigestOutput` call per day (sanctioned Invariant 1 extension). All other invariants unchanged.
- Migration notes: N/A — new tables (`reports`) created by `init_db()` via `CREATE TABLE IF NOT EXISTS`.
- Related PR/commit: phase-3-automated-delivery branch

## 2026-06-12 — Phase 2: source ingestion + retrieval

Summary:

- What changed: `ingestion/rss.py` (httpx + feedparser + trafilatura fetcher with error-count deactivation at 5), `analyst/triage.py` (batched triage via `settings.triage.id`, 20 items/chunk, one retry, score < 0.2 → `skipped`), `retrieval/search.py` (FTS5 `related_observations`/`related_items` with ×1.5 recency boost), `analyst/theses.py` (`get_stale_theses` + `render_thesis_fragment`), `config.py` (`sync_config` — YAML is source of truth for topic/source definitions), `cli.py` (`analyst topic add`, `analyst source add`).
- Behavior: analyst prompt gains an always-present "Stale theses — revisit or retire" section and per-item "Related prior context" blocks. Item lifecycle: `new` → `skipped` (triage) | `analyzed` (marked inside the memory-write transaction).
- Fixes found by live smoke testing: Pydantic `ge`/`le` bounds removed from analyst output schemas (providers reject `minimum`/`maximum` in structured-output JSON schemas; clamping validators enforce ranges client-side), and parsed output is read from `response.choices[0].message.parsed` (the real SDK shape; the old `response.parsed` never existed).
- Testing: `pytest` runs the unit suite (smoke excluded by default); `pytest -m smoke` runs a live end-to-end pipeline against real feeds (needs `OPENROUTER_API_KEY`).
- Migration notes: replace placeholder `config/*.yaml` entries — `sync_config` deactivates DB rows absent from YAML (inbox-type sources exempt).
- Related PR/commit: phase-2-ingestion-retrieval branch

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
