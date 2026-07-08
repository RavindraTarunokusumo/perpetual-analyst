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

- `src/perpetual_analyst/analyst/`: ★ the product — agent, memory, theses, triage, schemas, prompts, discovery
- `src/perpetual_analyst/analyst/discovery.py`: weekly source discovery — `discover_sources`, `mine_outbound_domains`, `web_search_extra` provider seam
- `src/perpetual_analyst/ingestion/`: fetchers (rss, inbox, web)
- `src/perpetual_analyst/retrieval/`: FTS5 search helpers
- `src/perpetual_analyst/store/`: SQLite connection, migrations, row models
- `src/perpetual_analyst/report/`: assembly, rendering, citation conversion; `_record_citations` records cited items post-assembly
- `src/perpetual_analyst/delivery/`: Telegram send
- `src/perpetual_analyst/quality.py`: per-source quality scoring — `compute_source_quality`, `bottom_decile`, `transition_probation`
- `src/perpetual_analyst/daily_run.py`: daily orchestrator entry point
- `src/perpetual_analyst/weekly_run.py`: weekly compaction + discovery + quality-scoring orchestrator
- `src/perpetual_analyst/analyst/compaction.py`: observation expiry, weekly review model call, transactional apply
- `src/perpetual_analyst/cli.py`: typer CLI (`analyst topic add`, `analyst run`, `analyst weekly`, `analyst source candidates`)
- `config/`: `topics.yaml`, `sources.yaml`
- `inbox/`: manual document drop, per-topic subfolders
- `data/`: `analyst.db`, `reports/`
- `tests/`: test suite
- `TODO.md`: active work only
- `session_ledger.json`: active session status, blockers, handoffs, validation, reviews
- `docs/iterations/archive/`: completed TODO archive
- `docs/specs/`: accepted specs and plans for active/future implementation
- `SPEC.md`: authoritative architecture specification

## Fast Path By Task

- Changing analyst behavior: read `architecture.md` → `analyst/agent.py` → `analyst/prompts/`
- Changing memory logic: read `database.md` → `analyst/memory.py` → `analyst/theses.py`
- Changing compaction / observation lifecycle: read `database.md` → `analyst/compaction.py` → `weekly_run.py`
- Changing source discovery or quality scoring: read `architecture.md` → `analyst/discovery.py` → `quality.py` → `weekly_run.py`
- Changing source candidate approval: read `architecture.md` → `analyst/candidates.py` → `web.py` → `database.md`
- Changing DB schema: read `database.md` → `store/db.py` (full DDL in `init_db()`)
- Changing ingestion: read `architecture.md` → `ingestion/` module
- Changing delivery: read `architecture.md` → `delivery/telegram.py`
- Running the system: read `commands.md`
- Preparing for review: read `AGENTS.md`, `testing.md`, and PR template
- Starting implementation: read `docs/specs/README.md` and the active accepted spec under `docs/specs/`

## Core Invariants

- **One analyst call per topic per day.** No multi-agent patterns.
- Memory budgets are enforced by the context assembler, not by the model.
- Theses are never silently edited — every revision logs to `thesis_updates`.
- `≤7 active theses` per topic is a hard DB-enforced constraint.
- `nothing_significant: bool` is a first-class output field — never suppress it.
- All analyst memory writes are transactional (observations + thesis updates + dossier edits in one commit).
- `content_hash` is the dedupe key for items — duplicate inserts silently skip.
- Runtime secrets (API keys) must never appear in logs or stdout.
- No vectors, knowledge graphs, or rerankers in V1 — FTS5 only.
