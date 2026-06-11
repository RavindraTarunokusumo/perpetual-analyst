# TODO.md

This file contains active or future work only.
Completed sessions must be moved to `docs/iterations/archive/`.

---

## Session: Phase 2 — Source Ingestion + Retrieval (active — spec: docs/superpowers/specs/2026-06-11-phase-2-ingestion-retrieval-design.md)

### Task 6 — Thesis lifecycle
- [x] Implement `analyst/theses.py`: apply `ThesisUpdate`s (create/revise/retire) (regression-tested; CRUD lives in memory.py per spec)
- [x] Enforce ≤7 active theses per topic (raise on 8th)
- [ ] Stale-flagging query: any thesis untouched for 30 days flagged to analyst (query done; context wiring pending)
- [ ] Render "Thesis updates" fragment with confidence before→after

### Task 7 — RSS ingestion + triage
- [ ] Implement `ingestion/rss.py`: feedparser + trafilatura, since-last-fetch, error counting
- [ ] Implement `analyst/triage.py`: Haiku batch call — score (0–1) + 2-line summary per item
- [ ] Mark triaged items `status='analyzed'` or `status='skipped'`

### Task 8 — Retrieval
- [ ] Implement `retrieval/search.py`: `related_observations(text, topic, k)` and `related_items(text, topic, k)` using FTS5
- [ ] Recency weighting in FTS queries
- [ ] Wire "related prior context" blocks into agent context assembly

### Task 8.5 — Sources/topics config + CLI (extension added 2026-06-11, approved)
- [ ] Extend `config.py`: `TopicConfig`/`SourceConfig` loaders + idempotent `sync_config()` (YAML → DB upsert)
- [ ] CLI: `analyst topic add` and `analyst source add` (append to YAML, re-sync)
- [ ] Replace placeholder YAML entries with real "AI frontier labs" topic + 2-3 RSS feeds
- [ ] Live smoke test (`pytest -m smoke`): real feeds → triage → one analyst run on scratch DB

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
