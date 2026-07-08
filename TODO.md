# TODO.md

This file contains active or future work only.
Completed sessions must be moved to `docs/iterations/archive/`.

---

## Active Session — Firecrawl source extraction pipeline

**Spec:** `docs/specs/2026-07-08-firecrawl-source-extraction.md` (accepted)
**Plan:** `docs/specs/2026-07-08-firecrawl-source-extraction-plan.md`
**Branch:** `firecrawl-source-extraction`
**Worktree:** `.worktree/firecrawl-source-extraction`
**Base:** `main` @ `ba94e0e`

### Carried WIP (uncommitted)

- [ ] `extract.py` — httpx + trafilatura `extract_url()` with bot-wall detection
- [ ] `pa_inspect.py` — wired to shared `extract_url`
- [ ] `tests/test_extract.py` — 3 unit tests (mocked httpx)
- [ ] `substrate.py` — `get_or_create_watch_topic(name: str | None)` fix

### Planned scope (pending spec acceptance)

- [ ] Firecrawl `/scrape` integration for article text extraction
- [ ] Fallback strategy: trafilatura first vs Firecrawl-first vs Firecrawl-on-failure
- [ ] Wire into `rss.py` `_extract_text` and any other extraction call sites
- [ ] `FIRECRAWL_API_KEY` in `.env.example`; secret logging invariant
- [ ] Live smoke test for a bot-protected URL (e.g. Reuters)
- [ ] Unit tests with mocked Firecrawl client

### Implementation tasks (from plan)

- [ ] T0 — Commit carried WIP (extract base + pa_inspect + tests; substrate fix separate)
- [ ] T1 — `firecrawl-py` dep + `.env.example` + never-log invariant
- [ ] T2 — Firecrawl fallback in `extract_url`
- [ ] T3 — Wire `rss.py` to `extract_url`
- [ ] T4 — Live smoke test (`pytest -m smoke`)
- [ ] T5 — Final validation + PR

### Blockers / notes

- GitNexus: repo not indexed (`gitnexus analyze` needed on clean tree)
- Step 3 planning complete — awaiting implementation go-ahead or Autopilot Mode

---

## Future Backlog

### From the PA ↔ Nexus integration (2026-07-08)

- [ ] **Cross-topic dedupe hides shared corpus** (documented spec §10). Global `content_hash` dedupe gives a document one `scope`; a source item shared across topics is invisible to later topics. Needs a schema change — per-topic document rows or a `scope` join-table — so defer until multi-topic shared sources become common.
- [ ] **Third-party source-rating API.** Replace the retired citation/uniqueness/freshness quality signals (dead since the FTS citation path was removed). Seam: `quality.compute_source_quality` (currently scores on `hit_rate` only).
- [ ] **`substrate.ingest` true atomicity.** Currently compensating-delete on span-ingest failure; a hard crash between the document commit and span ingest can still orphan a document. True atomicity needs a session-based `ingest_sentence_spans` upstream in Nexus.

### Pre-existing

- [ ] Web UI: source-candidate approval flow (approve/dismiss discovered candidates; SSRF/validation on approved-URL fetch), source/quality dashboard. Supersedes the deferred Telegram approval buttons.
- [ ] Discovery metrics: add uniqueness (sole-source-for-a-cited-development) + freshness-lead to `quality_score` (deferred from Phase 5; note these also depend on the citation/provenance signal being restored).
- [ ] Discovery provider: optionally swap OpenRouter web search → Perplexity (seam = `analyst.discovery.web_search_extra` + `analyst.agent.make_client`).

---

## Archived sessions

- Phase 1 — `docs/iterations/archive/2026-06-10-phase-1-analyst-prototype.md`
- Phase 2 + 3 + CLI — `docs/iterations/archive/2026-06-10-phase-2-3-cli.md`
- Phase 4 (memory & thesis maturity) — `docs/iterations/archive/2026-06-11-phase-4-compaction.md`
- Phase 5 (source discovery & quality) — `docs/iterations/archive/2026-06-11-phase-5-discovery.md`
- PA ↔ Nexus integration — `docs/iterations/archive/2026-07-08-pa-nexus-integration.md` (PA #9 / Nexus #33)
