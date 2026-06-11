# TODO.md

This file contains active or future work only.
Completed sessions must be moved to `docs/iterations/archive/`.

---

## Session: phase-5-discovery (active)

Phase 5 — Source discovery & quality (SPEC §11). Branch off `phase-1-analyst-prototype`.
Approval UI deferred to a future Web UI session (no Telegram inbound listener this phase) —
discovery only *proposes* candidates; sources are never auto-added/removed. Discovery uses
OpenRouter web search behind a provider seam (swappable to Perplexity later). Metrics this
phase: triage hit-rate + citation rate (uniqueness/freshness-lead deferred).

### Task A — Schema: citations, source_candidates, sources probation columns
- [x] `store/db.py`: `citations` + `source_candidates` tables; `status`/`probation_until` columns on `sources` — 58373aa
- [x] `store/db.py`: idempotent `_ensure_columns` migration (guarded via `PRAGMA table_info`) — 58373aa
- [x] `store/models.py`: `Citation`, `SourceCandidate` dataclasses; extend `Source` — 58373aa
- [x] Tests: fresh-DB schema, migration, model round-trips — 669a2de

### Task B — Citation recording at report assembly
- [x] `report/assemble.py`: record each cited `[item:N]` → `citations` (item_id→source_id, report_date); dedupe via INSERT OR IGNORE — 3e992c0
- [x] Tests: cited items recorded with correct source_id; uncited absent; re-assembly idempotent — 3db93ff

### Task C — Per-source quality metrics → quality_score
- [x] `quality.py::compute_source_quality(conn)`: triage hit-rate + citation rate → `sources.quality_score`; skip zero-item sources — 929fd99
- [x] `quality.py::bottom_decile(conn)` — worst sources for drop recommendations; probation excluded — 929fd99
- [x] Tests: hit-rate/citation-rate math, quality_score written, probation excluded — b86f661

### Task D — Discovery run (link-mining + OpenRouter web search)
- [x] `analyst/discovery.py::mine_outbound_domains(topic_id, conn)`: domains from cited items' URLs, ranked — 62e3e6c
- [x] `analyst/schemas.py::DiscoveryOutput` / `DiscoveryCandidate` — f3cc358
- [x] `analyst/prompts/discovery.md` prompt — f3cc358
- [x] `discovery.py::discover_sources(...)`: web-search model call behind `web_search_extra` seam; store `source_candidates` — 62e3e6c
- [x] Tests with mock client: candidates stored, dry-run skips, seam contract, dedupe — 62e3e6c

### Task E — Weekly integration + surfacing + probation lifecycle + CLI
- [x] `weekly_run.py`: per-topic `discover_sources`; post-loop `compute_source_quality` + bottom-decile drop recs + `transition_probation` — f159351
- [x] `quality.py::transition_probation(conn)` — probation→active after window — c6826f6
- [x] `cli.py`: `source candidates` read-only view; `source add` starts in `probation` (+21 days) — a3e85b3
- [x] Tests: weekly wiring, probation transition, CLI candidate listing — c6826f6, f159351, a3e85b3

---

## Archived sessions

- Phase 1 — `docs/iterations/archive/2026-06-10-phase-1-analyst-prototype.md`
- Phase 2 + 3 + CLI — `docs/iterations/archive/2026-06-10-phase-2-3-cli.md`
- Phase 4 (memory & thesis maturity) — `docs/iterations/archive/2026-06-11-phase-4-compaction.md`
