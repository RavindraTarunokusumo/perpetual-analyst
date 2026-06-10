# TODO.md

This file contains active or future work only.
Completed sessions must be moved to `docs/iterations/archive/`.

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
