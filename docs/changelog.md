# Changelog

Record notable behavior, architecture, API, persistence, or workflow changes.

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
