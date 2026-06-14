# TODO.md

This file contains active or future work only.
Completed sessions must be moved to `docs/iterations/archive/`.

---

## Future Backlog

- [ ] Phase 4: Weekly compaction run (promotion/expiry), stale-thesis flagging, prompt-caching pass
- [ ] Phase 5: Per-source quality metrics, weekly discovery run, Telegram approval buttons
- [ ] Embeddings upgrade: sqlite-vec + Voyage (only when FTS proves insufficient)
- [ ] (Phase 3 follow-up) Cap retry_undelivered per-run delivery count — first run after credentials appear delivers the entire backlog at once (Telegram rate-limit risk). Deferred operability, not correctness.
- [ ] (Web UI follow-up) Thesis retire/flag action from the dashboard — deferred from V1; must write a `thesis_updates` audit row (Invariant 3).
- [ ] (Web UI follow-up) Add-inbox URL fetching — V1 is text-only; fetch + extract a pasted URL (reuse `ingestion/extract.py`) in the background rather than in-request.
- [ ] (Web UI follow-up) Sanitize report markdown (`bleach`/safe-mode) if reports ever incorporate untrusted HTML — currently rendered with `|safe` (analyst-controlled, loopback-only).
