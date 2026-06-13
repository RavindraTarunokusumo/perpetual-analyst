# TODO.md

This file contains active or future work only.
Completed sessions must be moved to `docs/iterations/archive/`.

---

## Session: Web UI Dashboard (in progress)

Flask + Jinja local single-user dashboard over the existing SQLite data.
Spec: `docs/superpowers/specs/2026-06-14-web-ui-dashboard-design.md`
Plan: `docs/superpowers/plans/2026-06-14-web-ui-dashboard.md`

- [ ] Task 1: Scaffold package, deps (flask, markdown), app factory + Today page
- [ ] Task 2: Reports archive + report detail
- [ ] Task 3: Topics list, topic detail, thesis history
- [ ] Task 4: Items feed (filterable) + Ops overview
- [ ] Task 5: Global Reading mode (stacked dossiers)
- [ ] Task 6: Add-inbox write action
- [ ] Task 7: Retry-undelivered write action
- [ ] Task 8: Trigger-run action (single-run lock + background thread + status poll)
- [ ] Task 9: `analyst web` CLI command
- [ ] Task 10: Full-suite gate + lint

Notes / deviations:
- Add-inbox narrowed to text-required (URL optional metadata); in-request URL
  fetching deferred. Logged per Workflow Rule 2.
- No thesis-edit action in V1 (keeps Invariant 3 untouched).

---

## Future Backlog

- [ ] Phase 4: Weekly compaction run (promotion/expiry), stale-thesis flagging, prompt-caching pass
- [ ] Phase 5: Per-source quality metrics, weekly discovery run, Telegram approval buttons
- [ ] Embeddings upgrade: sqlite-vec + Voyage (only when FTS proves insufficient)
- [ ] (Phase 3 follow-up) Cap retry_undelivered per-run delivery count — first run after credentials appear delivers the entire backlog at once (Telegram rate-limit risk). Deferred operability, not correctness.
