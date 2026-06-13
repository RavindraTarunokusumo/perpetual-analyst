# TODO.md

This file contains active or future work only.
Completed sessions must be moved to `docs/iterations/archive/`.

---

## Session: Web UI (next — out of SPEC v1, brainstorm pending)

Dashboard over the existing SQLite data (reports, theses, observations, items). Brainstorm scope/stack before implementing.

---

## Future Backlog

- [ ] Phase 4: Weekly compaction run (promotion/expiry), stale-thesis flagging, prompt-caching pass
- [ ] Phase 5: Per-source quality metrics, weekly discovery run, Telegram approval buttons
- [ ] Embeddings upgrade: sqlite-vec + Voyage (only when FTS proves insufficient)
- [ ] (Phase 3 follow-up) Cap retry_undelivered per-run delivery count — first run after credentials appear delivers the entire backlog at once (Telegram rate-limit risk). Deferred operability, not correctness.
