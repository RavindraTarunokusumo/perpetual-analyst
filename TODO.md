# TODO.md

This file contains active or future work only.
Completed sessions must be moved to `docs/iterations/archive/`.

---

## Future Backlog

- [ ] Web UI: source-candidate approval flow (approve/dismiss discovered candidates; SSRF/validation on approved-URL fetch), source/quality dashboard. Supersedes the deferred Telegram approval buttons.
- [ ] Discovery metrics: add uniqueness (sole-source-for-a-cited-development) + freshness-lead to `quality_score` (deferred from Phase 5).
- [ ] Discovery provider: optionally swap OpenRouter web search → Perplexity (seam = `analyst.discovery.web_search_extra` + `analyst.agent.make_client`).
- [ ] Embeddings upgrade: sqlite-vec + Voyage (only when FTS proves insufficient)

---

## Archived sessions

- Phase 1 — `docs/iterations/archive/2026-06-10-phase-1-analyst-prototype.md`
- Phase 2 + 3 + CLI — `docs/iterations/archive/2026-06-10-phase-2-3-cli.md`
- Phase 4 (memory & thesis maturity) — `docs/iterations/archive/2026-06-11-phase-4-compaction.md`
- Phase 5 (source discovery & quality) — `docs/iterations/archive/2026-06-11-phase-5-discovery.md`
