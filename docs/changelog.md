# Changelog

Record notable behavior, architecture, API, persistence, or workflow changes.

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
