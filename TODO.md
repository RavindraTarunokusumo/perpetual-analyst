# TODO.md

This file contains active or future work only.
Completed sessions must be moved to `docs/iterations/archive/`.

---

## Session: phase-4-compaction (active)

Phase 4 — Memory & thesis maturity (SPEC §12). Branch off `phase-1-analyst-prototype`.
The weekly compaction is a **separate weekly run** (one analyst call/topic/week) — a distinct
cadence from the daily call, consistent with Invariant #1 (no daily critic loop).

### Task A — Observation expiry (structural, no model)
- [x] `analyst/compaction.py::expire_observations(conn, topic_id=None) -> int`: importance-1 active obs older than 30d and importance-2 older than 90d → `status='expired'`; importance-3 never expires; returns count — ef0674c
- [x] Tests: expiry boundaries (29/31d for imp-1, 89/91d for imp-2), imp-3 immunity, already-expired/promoted skipped — ef0674c

### Task B — Promotion: schema + model call + transactional apply
- [x] `analyst/schemas.py::WeeklyReviewOutput` (dossier_rewrite, promoted_observation_ids, notes) — 2e0819d
- [x] Fill in `analyst/prompts/weekly_review.md` (promotion + self-review note, JSON output contract) — 2e0819d
- [x] `compaction.py::run_weekly_review(topic, conn, client, settings, dry_run) -> WeeklyReviewOutput | None` (create()+model_validate_json, mirrors run_topic) — cdbdec6
- [x] `compaction.py::apply_weekly_review(topic_id, output, conn)`: transactional (`with conn:`) dossier rewrite + mark promoted obs `status='promoted'` — cdbdec6
- [x] Tests with mock client + transactional-rollback test — cdbdec6

### Task C — Weekly run orchestrator + CLI
- [x] `weekly_run.py`: per active topic → expire_observations, run_weekly_review, apply_weekly_review; log structural stale-thesis flags via `get_stale_theses`; `--dry-run`, `--topic` — 272d667
- [x] `cli.py::weekly` command mirroring `run` — bfc86bc
- [x] Tests for orchestrator (dry-run skips client, error isolation per topic) — 272d667

### Task D — Surface stale flags + thesis audit trail in daily context
- [x] `analyst/theses.py::render_thesis_trail(topic_id, conn)`: from `thesis_updates`, render `confidence 0.60→0.80 over N updates` — 1e6495a
- [x] `agent.py::assemble_context`: replace manual theses_text with `render_thesis_fragment` (stale markers) + append per-thesis trail — f4be42e
- [x] Tests: stale marker present in context, trail string format — 1e6495a, f4be42e

### Task E — Prompt-caching pass (stable prefix ordering)
- [x] Reorder `assemble_context` user message: stable prefix first (brief, dossier, active theses), volatile last (yesterday's report, related context, today's items) — f0cecc4
- [x] Attach `cache_control` breakpoint(s) for OpenRouter/Anthropic prompt caching on the stable prefix — f0cecc4
- [x] Tests: assert ordering and cache_control presence — f0cecc4

---

## Session: phase-2-cli-and-ingestion (active)

### Task 5 — CLI
- [x] Implement `cli.py`: topic add/list, source add/list, run, report show — e847fe2
- [x] Fix Windows dry-run Unicode encoding — e1fa262
- [ ] Exit test: 5-day inbox simulation (needs OPENROUTER_API_KEY in .env; scaffold in exit-test/)

---

## Session: Phase 2 — Source Ingestion + Retrieval (completed in phase-2-cli-and-ingestion)

### Task 6 — Thesis lifecycle
- [x] Implement `analyst/theses.py`: apply `ThesisUpdate`s (create/revise/retire) — (memory.py already)
- [x] Enforce ≤7 active theses per topic (raise on 8th) — (memory.py already)
- [x] Stale-flagging query: `get_stale_theses()` — theses untouched >30 days — 59f806b
- [x] Render thesis fragment with confidence % and stale markers — `render_thesis_fragment()` — 59f806b

### Task 7 — RSS ingestion + triage
- [x] Implement `ingestion/rss.py`: feedparser + trafilatura, since-last-fetch, error counting — 8fcf423
- [x] Implement `analyst/triage.py`: triage model batch call — score (0–1) + 2-line summary per item — 8fcf423
- [x] Mark triaged items `status='analyzed'` or `status='skipped'` — 8fcf423

### Task 8 — Retrieval
- [x] Implement `retrieval/search.py`: `related_observations(text, topic, k)` and `related_items(text, topic, k)` using FTS5 — 89955e3
- [x] Recency weighting in FTS queries (30-day obs boost, 14-day item boost) — 89955e3
- [x] Wire "Related prior observations" and "Related prior items" blocks into `assemble_context` — 89955e3

---

## Session: Phase 3 — Automated Delivery (completed in phase-2-cli-and-ingestion)

### Task 9 — Report assembly + rendering
- [x] Implement `report/assemble.py`: merge topic sections, build exec summary — b1192f2
- [x] Implement `report/render.py`: `[item:N]` → footnote conversion (batched IN query) — b1192f2
- [x] Write `analyst/prompts/digest.md` for Telegram digest generation — b1192f2
- [x] Write `reports` DB row + markdown file to `data/reports/` — b1192f2

### Task 10 — Telegram delivery + scheduler
- [x] Implement `delivery/telegram.py`: HTML digest ≤3,000 chars + document attach — c2adc41
- [x] Retry logic for undelivered reports (check `delivered_at IS NULL`) — c2adc41
- [x] Implement `daily_run.py` orchestrator: ingest→triage→analyze-per-topic→assemble→deliver with per-stage error isolation — c2adc41
- [x] Document cron / Windows Task Scheduler entry in `docs/commands.md` — (see docs/commands.md)

---

## Future Backlog

- [ ] Phase 4: Weekly compaction run (promotion/expiry), stale-thesis flagging, prompt-caching pass
- [ ] Phase 5: Per-source quality metrics, weekly discovery run, Telegram approval buttons
- [ ] Embeddings upgrade: sqlite-vec + Voyage (only when FTS proves insufficient)
