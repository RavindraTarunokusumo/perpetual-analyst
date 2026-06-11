# Session Archive: phase-5-discovery

**Merged:** PR #5 — commit merge `545c9ea` into `phase-1-analyst-prototype`
**Branch:** `phase-5-discovery`
**Date:** 2026-06-11
**Phase:** 5 — Source discovery & quality (SPEC §11)

---

## Outcome

Per-source quality scoring, a weekly web-search discovery run that proposes candidate sources,
and a probation lifecycle. **Approval deferred to a future Web UI** — sources are never
auto-added/removed; discovery only proposes candidates (stored `pending`). No Telegram inbound
listener this phase. Discovery uses OpenRouter web search behind the `web_search_extra` provider
seam (swappable to Perplexity later). Metrics: triage hit-rate + citation rate
(uniqueness/freshness-lead deferred).

Validated by a **live smoke test** (Workflow Rule 11) against `anthropic/claude-opus-4-8` +
OpenRouter web search: quality scoring matched expectations, discovery returned 5 real on-topic
sources. The smoke test caught a real provider bug (web plugin ignores `response_format=json_object`
and prepends prose) that all mocked tests missed — fixed with tolerant JSON extraction. 175 tests.

---

## Tasks

### Task A — Schema: citations, source_candidates, sources probation columns
- [x] `citations` + `source_candidates` tables; `sources.status`/`probation_until` columns — 58373aa
- [x] idempotent `_ensure_columns` migration (PRAGMA-guarded) — 58373aa
- [x] `Citation`/`SourceCandidate` models; extend `Source` — 58373aa
- [x] Tests: fresh-DB schema, migration, model round-trips — 669a2de

### Task B — Citation recording at report assembly
- [x] `report/assemble.py::_record_citations` + `render.py::cited_item_ids`; INSERT OR IGNORE — 3e992c0
- [x] Tests: correct source_id, uncited absent, idempotent — 3db93ff

### Task C — Per-source quality metrics → quality_score
- [x] `quality.py::compute_source_quality` (hit-rate + citation rate → quality_score) — 929fd99
- [x] `quality.py::bottom_decile` (drop candidates, probation excluded) — 929fd99
- [x] Tests: rate math, persistence, probation excluded — b86f661

### Task D — Discovery run (link-mining + OpenRouter web search)
- [x] `discovery.py::mine_outbound_domains` — f3cc358, 62e3e6c
- [x] `schemas.py::DiscoveryOutput`/`DiscoveryCandidate`; `prompts/discovery.md` — f3cc358
- [x] `discovery.py::discover_sources` (web-search seam, candidate storage) — 62e3e6c
- [x] Tests with mock client (storage, dry-run, seam, dedupe) — 62e3e6c
- [x] Fix (found by live smoke test): tolerant JSON extraction for prose-wrapped web-search replies — 9b910a6

### Task E — Weekly integration + probation lifecycle + CLI
- [x] `weekly_run.py`: per-topic discovery + post-loop quality/bottom-decile/probation pass — f159351
- [x] `quality.py::transition_probation` — c6826f6
- [x] `cli.py`: `source candidates` view; `source add` starts in probation (+21d) — a3e85b3
- [x] Tests: weekly wiring, probation transition, CLI listing — c6826f6, f159351, a3e85b3

---

## Post-implementation (Pre-PR)
- `/simplify` (4 agents): pass precomputed scores into `bottom_decile` (no double compute), `executemany`, single regex scan, `Counter` mining, single CLI query, seam co-change TODO — (committed pre-merge)
- doc-updater: architecture, database, commands, index, patterns, changelog — c57acf7
- Live smoke test → discovery JSON-extraction fix — 9b910a6

## Invariants preserved
- **#1** one analyst call/topic/day — discovery is a separate weekly call.
- **#5** transactional writes — quality/citation/discovery/probation writes use `with conn:`.
- **#7** no secrets logged — logs emit only slugs, counts, row IDs.

## Note for a future phase
When the deferred Web-UI approval is built, *approving* a candidate means fetching a
model-proposed URL — handle SSRF/validation there.
