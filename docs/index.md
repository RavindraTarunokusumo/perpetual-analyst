# Documentation Index

Use this file as the second layer after `AGENTS.md`. It points to deeper docs without repeating them.

## Core Docs

- [agent-harness.md](agent-harness.md): agent-facing documentation structure and harness rules
- [architecture.md](architecture.md): system design, module boundaries, entry points, data flow
- [database.md](database.md): schema, memory tiers, migration rules
- [patterns.md](patterns.md): durable coding rules, memory patterns, anti-patterns from SPEC §15
- [testing.md](testing.md): test execution, fixtures, validation workflow
- [commands.md](commands.md): common local commands, CLI reference
- [changelog.md](changelog.md): notable behavior and architecture changes
- [insights.md](insights.md): session lessons and reusable workflow observations
- [specs/README.md](specs/README.md): active accepted spec workflow

## Module Docs

Add module-specific docs here as the codebase grows:

- [utils/](utils/)

## Repo Areas

- `src/perpetual_analyst/substrate.py`: ★ Nexus boundary — ingest, retrieve, synthesize, persist_bundle, answer, resolve_lifecycle
- `src/perpetual_analyst/analyst/synthesis.py`: daily narrative-update loop entry point
- `src/perpetual_analyst/analyst/`: triage, schemas (`NarrativeUpdate`), compaction, discovery, memory (weekly SQLite path)
- `src/perpetual_analyst/analyst/discovery.py`: weekly source discovery — `discover_sources`, `mine_outbound_domains`, `web_search_extra` provider seam
- `src/perpetual_analyst/ingestion/`: fetchers (rss, inbox, web)
- `src/perpetual_analyst/store/`: SQLite connection, migrations, row models (operational tables)
- `src/perpetual_analyst/report/`: `assemble.py` — joins `NarrativeUpdate.briefing_markdown` per topic; no citation conversion
- `src/perpetual_analyst/delivery/`: Telegram send
- `src/perpetual_analyst/quality.py`: per-source quality scoring — `compute_source_quality`, `bottom_decile`, `transition_probation`
- `src/perpetual_analyst/daily_run.py`: daily orchestrator entry point
- `src/perpetual_analyst/weekly_run.py`: weekly compaction + discovery + quality-scoring orchestrator
- `src/perpetual_analyst/analyst/compaction.py`: observation expiry, weekly review model call, transactional apply (SQLite)
- `src/perpetual_analyst/cli.py`: typer CLI (`analyst topic add`, `analyst run`, `analyst ask`, `analyst score`, `analyst weekly`, `analyst source candidates`)
- `Nexus/`: git submodule — Postgres schema, sentence-window retrieval, Embedder, LLMClient
- `config/`: `topics.yaml`, `sources.yaml`, `settings.yaml`
- `inbox/`: manual document drop, per-topic subfolders
- `data/`: `analyst.db`, `reports/`
- `tests/`: test suite
- `TODO.md`: active work only
- `session_ledger.json`: active session status, blockers, handoffs, validation, reviews
- `docs/iterations/archive/`: completed TODO archive
- `docs/specs/`: accepted specs and plans for active/future implementation
- `SPEC.md`: authoritative architecture specification

## Fast Path By Task

- Changing daily analyst behavior: read `architecture.md` → `substrate.py` → `analyst/synthesis.py`
- Changing memory / analytical objects: read `database.md` → `substrate.py` (`persist_bundle`, `synthesize`)
- Changing retrieval or corpus ingest: read `architecture.md` → `substrate.py` → `Nexus/app/intelligence/sentence_window.py`
- Changing compaction / observation lifecycle (weekly SQLite path): read `database.md` → `analyst/compaction.py` → `weekly_run.py`
- Changing source discovery or quality scoring: read `architecture.md` → `analyst/discovery.py` → `quality.py` → `weekly_run.py`
- Changing source candidate approval: read `architecture.md` → `analyst/candidates.py` → `web.py` → `database.md`
- Changing SQLite ops schema: read `database.md` → `store/db.py` (full DDL in `init_db()`)
- Changing Postgres memory schema: read `database.md` → `Nexus/app/db/migrations/`
- Changing ingestion: read `architecture.md` → `ingestion/` module
- Changing delivery: read `architecture.md` → `delivery/telegram.py`
- Using the web dashboard: read `commands.md` → `web/app.py`
- Running the system: read `commands.md`
- Preparing for review: read `AGENTS.md`, `testing.md`, and PR template
- Starting implementation: read `docs/specs/README.md` and the active accepted spec under `docs/specs/`

## Core Invariants

- **One analyst call per topic per day.** The synthesis call (`substrate.synthesize`). Triage is a function, not an agent.
- Memory budgets are enforced structurally: sentence-window `top_k` caps retrieval; prior claims/hypotheses are recency-bounded in synthesis context.
- Hypotheses are never silently edited — prior active rows are retired; new snapshot inserted (≤7 active); history preserved as `retired` rows.
- `narrative_states` is the source of truth; dossier is a rendered projection (weekly SQLite path is legacy).
- `nothing_significant: bool` is a first-class output field — never suppress it.
- Daily analytical writes are transactional (`persist_bundle` — all Postgres objects in one commit).
- `content_hash` is the dedupe key for items/documents — duplicate inserts silently skip.
- Runtime secrets (`QWEN_CLOUD_API_KEY`, `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, etc.) must never appear in logs or stdout.
- Retrieval is Nexus sentence-window over pgvector spans, topic-scoped — not FTS5.