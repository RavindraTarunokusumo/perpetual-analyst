# TODO.md

This file contains active or future work only.
Completed sessions must be moved to `docs/iterations/archive/`.

---

## Active: PA ↔ Nexus integration

Spec: `docs/specs/2026-07-08-pa-nexus-integration.md`
Plan: `docs/specs/2026-07-08-pa-nexus-integration-plan.md`
Branch: `pa-nexus-integration` (PA) · Nexus-repo change on its own branch.

Environment blockers (gate Phases B–F validation/commit):
- No Postgres reachable in this env (`pg_isready` absent) — needed for migrations/ingest/loop.
- No `.env` / DashScope (Qwen) key at PA root — needed for live retrieval/synthesis.
- GitNexus MCP not loaded this session → impact analysis via direct source reads (CLAUDE.md fallback).

Tasks (per plan):
- [x] A1 — Qwen provider defaults + DashScope key + ruff-exclude Nexus (PA) — `b39a2b1`
- [x] N1 — corpus/topic-scoped retrieval, scope param default-None (Nexus repo) — `cd4be18` (branch pa-corpus-scope). Scope-filter integration test deferred until Postgres available.
- [x] D1 — NarrativeUpdate + analytical Pydantic schemas; deprecate TopicAnalysis (PA) — `429d88b`
- [x] A2 — `substrate.py` ingest+retrieve boundary (PA) — `16b1a06` (live-verified: scope isolation + dedupe)
- [x] B1 — analytical tables migration 0009 (Nexus repo) — `8a776a4` (round-trip + CASCADE verified; head=0009)
- [x] B2 — get_or_create_watch_topic (slug→topic_id) in substrate.py — `1aa126f`
- [x] C — daily ingest → corpus (triage kept) — `b16e209` (+ substrate loop fix `78b7be6`)
- [x] D1 — NarrativeUpdate schema; deprecate TopicAnalysis — `429d88b`
- [x] D2a — substrate.synthesize (retrieve + one qwen3.7-max NarrativeUpdate call) — `95cf947`
- [x] 0010 — claims.document_id nullable (Nexus) — `37e87b2`/`27ab8ff`
- [x] D2b — substrate.persist_bundle (transactional write) — `6414959` (2-day live: v1→v2, superseded, claim_evidence)
- [x] D3 — synthesis orchestration — `a22336c`
- [x] D4 — daily_run narrative loop + Qwen client + briefing via DTO — end-to-end verified
- [x] E1/E2 — cross-session `ask` + `score` (expire/decay) — CLI-verified (+ Nexus answer-scope `2ac181b`)
- [x] F1/F2 — retire FTS5/Voyage retrieval + old TopicAnalysis; drop dead deps — `544c1fb` (e2e re-verified: ingest→narrative v1→report from briefing_markdown)

---

## Future Backlog

- [ ] Web UI: source-candidate approval flow (approve/dismiss discovered candidates; SSRF/validation on approved-URL fetch), source/quality dashboard. Supersedes the deferred Telegram approval buttons.
- [ ] Discovery metrics: add uniqueness (sole-source-for-a-cited-development) + freshness-lead to `quality_score` (deferred from Phase 5).
- [ ] Discovery provider: optionally swap OpenRouter web search → Perplexity (seam = `analyst.discovery.web_search_extra` + `analyst.agent.make_client`).
- [ ] Embeddings upgrade: sqlite-vec + Voyage (only when FTS proves insufficient)

---

## Archived sessions

- Phase 1 — `docs/iterations/archive/2026-06-10-phase-1-analyst-prototype.md`
- Phase 2 + 3 + CLI — `docs/iterations/archive/2026-06-10-phase-2-3-cli.md`
- Phase 4 (memory & thesis maturity) — `docs/iterations/archive/2026-06-11-phase-4-compaction.md`
- Phase 5 (source discovery & quality) — `docs/iterations/archive/2026-06-11-phase-5-discovery.md`
