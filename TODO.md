# TODO.md

This file contains active or future work only.
Completed sessions must be moved to `docs/iterations/archive/`.

---

## Session: Phase 3 — Automated Delivery (active)

### Task 9 — Report assembly + rendering
- [x] Implement `report/assemble.py`: merge topic sections, build exec summary
- [x] Implement `report/render.py`: `[item:N]` → footnote conversion
- [x] Write `analyst/prompts/digest.md` for Telegram digest generation
- [x] Write `reports` DB row + markdown file to `data/reports/`

### Task 10 — Telegram delivery + scheduler
- [x] Implement `delivery/telegram.py`: HTML digest ≤3,000 chars + document attach
- [x] Retry logic for undelivered reports (check `delivered_at IS NULL`)
- [ ] Implement `daily_run.py` orchestrator: ingest→triage→analyze-per-topic→assemble→deliver with per-stage error isolation
- [ ] Document cron / Windows Task Scheduler entry in `docs/commands.md` (support both Windows and Linux per 2026-06-11 decision)
- [x] (extension 2026-06-12, handoff) select_analyst_items helper + fetch_error_count reset on reactivation + smoke test topic-scoping

Phase 2 final-review handoff notes for the orchestrator (2026-06-12):
- Extract a shared `select_analyst_items(topic_id, conn, limit)` helper (status='new' AND triage_score >= SKIP_THRESHOLD, scoped per topic via topic_sources) — smoke test currently selects globally, fine for one topic only
- Call `sync_config` at the start of every run, before fetch
- Enforce Invariant 1 (one analyst call per topic per day) — check `reports` row for today before run_topic
- Triage assumes one pass per day; re-triaging never un-skips items
- A YAML-reactivated source resumes at fetch_error_count=5; consider resetting the counter on reactivation

---

## Future Backlog

- [ ] Phase 4: Weekly compaction run (promotion/expiry), stale-thesis flagging, prompt-caching pass
- [ ] Phase 5: Per-source quality metrics, weekly discovery run, Telegram approval buttons
- [ ] Embeddings upgrade: sqlite-vec + Voyage (only when FTS proves insufficient)
