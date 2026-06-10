# Session Archive: phase-4-compaction

**Merged:** PR #4 — commit merge `9dee97a` into `phase-1-analyst-prototype`
**Branch:** `phase-4-compaction`
**Date:** 2026-06-11
**Phase:** 4 — Memory & thesis maturity (SPEC §12)

---

## Outcome

Weekly memory-compaction subsystem added as a **separate weekly cadence** (one analyst
call/topic/week, distinct from the daily run — Invariant #1 preserved). Daily context now
surfaces thesis maturity, and both call paths cache the stable system prefix.

Validated by a **live smoke test** against `anthropic/claude-opus-4-8` (Workflow Rule 11):
imp-1 observation expired, stale thesis flagged, 2 observations promoted, dossier rewritten
with a self-review note, `WeeklyReviewOutput` parsed cleanly, and the `cache_control`
breakpoint on the weekly call was accepted by OpenRouter. 117 unit tests passing.

---

## Tasks

### Task A — Observation expiry (structural, no model)
- [x] `analyst/compaction.py::expire_observations(conn, topic_id=None) -> int`: imp-1 active >30d, imp-2 >90d → `status='expired'`; imp-3 immune; returns count — ef0674c
- [x] Tests: expiry boundaries (29/31d, 89/91d), imp-3 immunity, promoted/expired skipped — ef0674c

### Task B — Promotion: schema + model call + transactional apply
- [x] `analyst/schemas.py::WeeklyReviewOutput` (dossier_rewrite, promoted_observation_ids, notes) — 2e0819d
- [x] Fill in `analyst/prompts/weekly_review.md` (promotion + self-review note, JSON contract) — 2e0819d
- [x] `compaction.py::run_weekly_review(...)` (create()+model_validate_json, mirrors run_topic) — cdbdec6
- [x] `compaction.py::apply_weekly_review(...)`: transactional dossier rewrite + mark obs `promoted` — cdbdec6
- [x] Tests with mock client + transactional-rollback test — cdbdec6

### Task C — Weekly run orchestrator + CLI
- [x] `weekly_run.py`: per topic → expire, run_weekly_review, apply; log stale-thesis flags; `--dry-run`/`--topic` — 272d667
- [x] `cli.py::weekly` command mirroring `run` — bfc86bc
- [x] Tests for orchestrator (dry-run skips client, per-topic error isolation) — 272d667

### Task D — Surface stale flags + thesis audit trail in daily context
- [x] `analyst/theses.py::render_thesis_trail(topic_id, conn)`: `confidence 0.60→0.80 over N update(s)` from `thesis_updates` — 1e6495a
- [x] `agent.py::assemble_context`: `render_thesis_fragment` (stale markers) + `## Thesis history` section — f4be42e
- [x] Tests: stale marker in context, trail string format — 1e6495a, f4be42e

### Task E — Prompt-caching pass (stable prefix ordering)
- [x] Reorder `assemble_context`: stable prefix first, volatile last — f0cecc4
- [x] `cache_control` breakpoint on the system prompt — f0cecc4
- [x] Tests: ordering + cache_control presence — f0cecc4

---

## Post-implementation (Pre-PR)

- `/simplify` (4 cleanup agents): shared `_with_cache_control` → public `with_cache_control`, applied on the weekly path so the stable weekly system prompt is also cached — dbd3b24
- Final-review nits: defer `make_client()` past empty-topics check; document expiry's separate commit boundary — (committed pre-merge)
- doc-updater: architecture, database, commands, index, patterns, changelog — daf7e3c

---

## Invariants preserved

- **#1** one analyst call/topic/day — weekly compaction is a separate weekly cadence, not a daily loop.
- **#2** memory structural — `build_memory_context` budget unchanged.
- **#3** theses never silently edited — weekly run never touches theses; only flags + promotes observations.
- **#5** transactional writes — `apply_weekly_review` single `with conn:` bundle (expiry commits separately by design: idempotent pure-SQL).
- **#7** no secrets logged — new logs emit only slugs, counts, row IDs.
