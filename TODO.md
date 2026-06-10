# TODO.md

This file contains active or future work only.
Completed sessions must be moved to `docs/iterations/archive/`.

---

## Session: Phase 1 — Analyst Prototype (2026-06-10)

Phase 1 exit test: *feed it 5 days of hand-picked articles one day at a time; day-5 report must reference day-1 context.*

### Task 1 — Project skeleton + DB layer
- [ ] Write `pyproject.toml` with all dependencies
- [ ] Create package layout under `src/perpetual_analyst/`
- [ ] Implement `store/db.py`: connection, `init_db()` running the full §5 DDL
- [ ] Add FTS5 `items_fts` and `observations_fts` virtual tables with triggers
- [ ] Write `store/models.py`: typed dataclasses or Pydantic models for DB rows
- [ ] Tests: schema creates clean, FTS triggers fire on insert/update/delete

### Task 2 — Memory module
- [ ] Implement `analyst/memory.py`: CRUD for dossier, observations, theses
- [ ] Implement `thesis_updates` audit writes in same transaction as thesis change
- [ ] Implement `build_memory_context(topic_id, token_budget)` — importance/recency sort, hard truncation
- [ ] Tests with fake in-memory DB data covering budget enforcement

### Task 3 — Analyst schemas + system prompt
- [ ] Finalize `analyst/schemas.py`: `TopicAnalysis`, `NewObservation`, `ThesisUpdate` Pydantic models
- [ ] Write `analyst/prompts/analyst_system.md` encoding all 12 behavioral rules from SPEC §7
- [ ] Ensure `nothing_significant: bool` is in schema and prompt

### Task 4 — Analyst agent call
- [ ] Implement `analyst/agent.py`: assemble context in caching-friendly order
- [ ] Wire `client.messages.parse()` with `claude-opus-4-8`, adaptive thinking
- [ ] Persist all returned memory writes transactionally after successful parse
- [ ] Implement `--dry-run` flag: print assembled prompt, skip API call
- [ ] Manual test: one topic, one item, check DB rows written

### Task 5 — Inbox ingestion
- [ ] Implement `ingestion/inbox.py`: scan `inbox/<topic-slug>/` for .md/.txt/.pdf
- [ ] Integrate `pypdf` for PDF text extraction
- [ ] Hash-dedupe on `content_hash` (SHA-256 of text), write `items` rows
- [ ] Mark ingested files as processed (rename or move to `inbox/<slug>/.processed/`)
- [ ] End-to-end Phase 1 test: 3 docs → analyst run → report file + memory rows written

---

## Session: Phase 2 — Source Ingestion + Retrieval (future)

### Task 6 — Thesis lifecycle
- [ ] Implement `analyst/theses.py`: apply `ThesisUpdate`s (create/revise/retire)
- [ ] Enforce ≤7 active theses per topic (raise on 8th)
- [ ] Stale-flagging query: any thesis untouched for 30 days flagged to analyst
- [ ] Render "Thesis updates" fragment with confidence before→after

### Task 7 — RSS ingestion + triage
- [ ] Implement `ingestion/rss.py`: feedparser + trafilatura, since-last-fetch, error counting
- [ ] Implement `analyst/triage.py`: Haiku batch call — score (0–1) + 2-line summary per item
- [ ] Mark triaged items `status='analyzed'` or `status='skipped'`

### Task 8 — Retrieval
- [ ] Implement `retrieval/search.py`: `related_observations(text, topic, k)` and `related_items(text, topic, k)` using FTS5
- [ ] Recency weighting in FTS queries
- [ ] Wire "related prior context" blocks into agent context assembly

---

## Session: Phase 3 — Automated Delivery (future)

### Task 9 — Report assembly + rendering
- [ ] Implement `report/assemble.py`: merge topic sections, build exec summary
- [ ] Implement `report/render.py`: `[item:N]` → footnote conversion
- [ ] Write `analyst/prompts/digest.md` for Telegram digest generation
- [ ] Write `reports` DB row + markdown file to `data/reports/`

### Task 10 — Telegram delivery + scheduler
- [ ] Implement `delivery/telegram.py`: HTML digest ≤3,000 chars + document attach
- [ ] Retry logic for undelivered reports (check `delivered_at IS NULL`)
- [ ] Implement `daily_run.py` orchestrator: ingest→triage→analyze-per-topic→assemble→deliver with per-stage error isolation
- [ ] Document cron / Windows Task Scheduler entry in `docs/commands.md`

---

## Future Backlog

- [ ] Phase 4: Weekly compaction run (promotion/expiry), stale-thesis flagging, prompt-caching pass
- [ ] Phase 5: Per-source quality metrics, weekly discovery run, Telegram approval buttons
- [ ] Embeddings upgrade: sqlite-vec + Voyage (only when FTS proves insufficient)
