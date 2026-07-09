# TODO.md

This file contains active or future work only.
Completed sessions must be moved to `docs/iterations/archive/`.

---

## Active session — Web UI refresh (2026-07-09)

Spec: `docs/specs/2026-07-09-web-ui-refresh.md` · Plan: `docs/specs/2026-07-09-web-ui-refresh-plan.md`
Branch: `web-ui-refresh` · Implementer: Grok junior handoff (one ephemeral session per task)

- [ ] T1 — Test enablement: restore `client`/seeded-DB fixtures so `tests/test_web_routes.py` + `tests/test_web_queries.py` collect and pass (no production changes)
- [ ] T2 — CSS tokens: ink-on-paper palette, semantic rise/fall colors, dark mode, mono tabular numerals, nav overflow, Reading view toggle
- [ ] T3 — Dossiers render as markdown (shared Jinja filter) on topic + reading pages
- [ ] T4 — Today "what changed" strip: thesis delta chips, new-observation counts, quiet nothing-significant lines, single load animation
- [ ] T5 — Thesis page: inline SVG confidence timeline from `thesis_updates`
- [ ] T6 — Topics index enrichment + Ops status pill + actionable empty states + link hygiene

## Future Backlog

### From the PA ↔ Nexus integration (2026-07-08)

- [ ] **Cross-topic dedupe hides shared corpus** (documented spec §10). Global `content_hash` dedupe gives a document one `scope`; a source item shared across topics is invisible to later topics. Needs a schema change — per-topic document rows or a `scope` join-table — so defer until multi-topic shared sources become common.
- [ ] **Third-party source-rating API.** Replace the retired citation/uniqueness/freshness quality signals (dead since the FTS citation path was removed). Seam: `quality.compute_source_quality` (currently scores on `hit_rate` only).
- [ ] **`substrate.ingest` true atomicity.** Currently compensating-delete on span-ingest failure; a hard crash between the document commit and span ingest can still orphan a document. True atomicity needs a session-based `ingest_sentence_spans` upstream in Nexus.

### From the Web UI polish session (2026-07-09)

- [ ] **Test suite does not collect on `main`.** Pre-existing refactor rot, unrelated to the UI work: `test_search` imports the deleted `retrieval` module; `test_smoke` imports missing `agent.run_topic`; `test_web_actions` imports removed `daily_run` symbols (`force_utf8_stdout`/`run_daily`); `test_web_queries`/`test_web_routes` depend on a removed `seeded_conn` fixture. Needs a dedicated cleanup to restore/remove these tests so `pytest` runs green.
- [ ] **`docs/commands.md` dashboard port is stale.** Line ~91 says default `http://127.0.0.1:8080`; the real default is `8765` (`cli.web` / `serve_dashboard`). One-line doc fix.

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
- Firecrawl source extraction — `docs/iterations/archive/2026-07-08-firecrawl-source-extraction.md` (PR #10 / `b982ab9`)
- Web UI polish + run-blocker fixes — `docs/iterations/archive/2026-07-09-web-ui-polish.md` (PR #11 / `f3eab3b`)
- Workflow hardening (CI gate + rules) — `docs/iterations/archive/2026-07-09-workflow-hardening.md` (PR #12 / `79ed66e`)