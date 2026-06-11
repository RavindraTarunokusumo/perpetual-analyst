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
- [ ] `store/db.py`: add `citations` table (report_id, report_date, item_id, source_id, created_at) and `source_candidates` table (topic_id, url, domain, rationale, status DEFAULT 'pending', created_at); add `status TEXT DEFAULT 'active'` and `probation_until TEXT` columns to `sources` DDL
- [ ] `store/db.py`: idempotent `_ensure_columns` migration — ALTER existing `sources` to add missing columns (guarded via `PRAGMA table_info`)
- [ ] `store/models.py`: add `Citation`, `SourceCandidate` dataclasses; extend `Source` with `status`, `probation_until`
- [ ] Tests: fresh-DB schema, migration adds columns to a pre-existing sources table, model round-trips

### Task B — Citation recording at report assembly
- [ ] `report/assemble.py`: after building full_markdown, record each cited `[item:N]` into `citations` (item_id → its source_id via items table, plus report_date); dedupe per (report_date, item_id)
- [ ] Tests: cited items recorded with correct source_id; uncited items absent; re-assembly idempotent

### Task C — Per-source quality metrics → quality_score
- [ ] `analyst/quality.py::compute_source_quality(conn) -> list[...]`: per source, triage hit-rate (items with triage_score ≥ 0.4 / total items) and citation rate (distinct cited items / total items); combine into `sources.quality_score`; skip sources with zero items
- [ ] `quality.py::bottom_decile(conn)` — sources ranked worst by score with item/citation counts for drop recommendations
- [ ] Tests: hit-rate/citation-rate math, quality_score written, probation sources flagged not dropped

### Task D — Discovery run (link-mining + OpenRouter web search)
- [ ] `analyst/discovery.py::mine_outbound_domains(topic_id, conn)`: domains from cited high-quality items' URLs, ranked by frequency
- [ ] `analyst/schemas.py::DiscoveryOutput` (candidates: list of {url, domain, rationale/gap})
- [ ] `analyst/prompts/discovery.md` prompt
- [ ] `discovery.py::discover_sources(topic, conn, client, settings, dry_run)`: model call via OpenRouter web search behind a provider seam (create()+model_validate_json); store results in `source_candidates`
- [ ] Tests with mock client: candidates stored, dry-run skips call, seam is swappable

### Task E — Weekly integration + surfacing + probation lifecycle + CLI
- [ ] `weekly_run.py`: after compaction, run `compute_source_quality` + `discover_sources`; print bottom-decile drop recs + new candidate count; transition probation sources past `probation_until` → `status='active'`
- [ ] `cli.py`: `analyst source candidates` (read-only list) and start `source add` sources in `status='probation'` with `probation_until = +21 days`
- [ ] Tests: weekly wiring, probation transition, CLI candidate listing

---

## Archived sessions

- Phase 1 — `docs/iterations/archive/2026-06-10-phase-1-analyst-prototype.md`
- Phase 2 + 3 + CLI — `docs/iterations/archive/2026-06-10-phase-2-3-cli.md`
- Phase 4 (memory & thesis maturity) — `docs/iterations/archive/2026-06-11-phase-4-compaction.md`
