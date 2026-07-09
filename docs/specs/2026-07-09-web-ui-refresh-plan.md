# Web UI Refresh — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Grok junior handoff per `AGENTS.md`
> §Grok Build Implementation/Review Handoff — the senior dev dispatches, reviews,
> validates, and commits; Grok implements. Fall back to direct implementation only with
> reason logged in `TODO.md`.

**Goal:** Ink-on-paper minimalist restyle + "confidence in motion" features (Today
changes strip, thesis SVG timeline, delta chips) for the local dashboard.

**Spec:** `docs/specs/2026-07-09-web-ui-refresh.md`

## Global constraints

- Worktree `.worktree/web-ui-refresh`, branch `web-ui-refresh`; editable install
  re-pointed (done in preamble); run tests with `PYTHONPATH=$PWD/src`.
- No external assets of any kind (fonts, scripts, images). No new dependencies.
- All new SELECTs in `web/queries.py`; no DB writes; no schema changes.
- Specific staging only; one commit per task; pre-commit from repo root.
- Pre-existing failures: 4 non-web collection errors are out of scope (Rule 9).
- GitNexus MCP absent this session — impact analysis by direct reads (recorded in
  `session_ledger.json`).

## Tasks (each = one Grok session, one commit)

- [ ] **T1 — Test enablement (S8).** Add `client` fixture to `tests/conftest.py`:
      seeded temp SQLite DB (reuse existing `db`/`sample_*` fixtures where possible) +
      `create_app(db_path).test_client()`. Target: `tests/test_web_routes.py` and
      `tests/test_web_queries.py` fully collect and pass. No production code changes.
- [ ] **T2 — Tokens + dark mode + hygiene (S1, S7-css).** Rewrite `:root` palette in
      `app.css` (ink/paper + semantic rise/fall tones), add `prefers-color-scheme: dark`
      block, `.num` mono-tabular class, right-aligned numeric table cells, nav
      `overflow-x: auto`, restyled buttons/badges/links per spec §2. Update `base.html`
      only for the "Reading view" toggle label/style.
- [ ] **T3 — Markdown dossiers (S2).** Lift `render_report_html` to module level as a
      `markdown` Jinja filter; use it in `topic.html` and `reading.html` (replace
      `<pre>`); routes unchanged. Tests: filter output for headings/lists; topic page
      renders dossier HTML.
- [ ] **T4 — Today changes strip (S3).** New `queries.today_changes(conn, report_date)`
      returning per-topic thesis deltas + new-observation counts + quiet topics; delta
      chip markup + staggered fade-up (reduced-motion-safe) in `today.html`/`app.css`;
      wire in `today` route. Tests: query on seeded fixtures; route 200 with and without
      a report.
- [ ] **T5 — Thesis timeline (S4).** Pure helper `confidence_points(updates, w, h)` →
      polyline coordinate string (step interpolation, `confidence_before` of first row as
      origin); inline `<svg>` in `thesis.html`; delta chips in the history table.
      Tests: points helper edge cases (0 updates, 1 update, null confidences).
- [ ] **T6 — Topics index + Ops + empty states (S5, S6, S7-rest).** Extend
      `topic_list` (last dossier update, top thesis, today's update count) +
      `topics.html` rows; ops status pill + disabled-while-running buttons +
      started/finished times; actionable empty states; `rel="noopener"` on external
      links. Tests: extended `topic_list` fields; ops page renders both states.

## Post-implementation

- [ ] Full validation: ruff, compileall, web test files, live `serve_dashboard` + curl
      smoke, light/dark visual check.
- [ ] `/code-review` before PR; fix blocking findings.
- [ ] PR via `.github/pull_request_template.md`; CI green before merge (Rule 16);
      merge commit, never squash (Rule 13); merge handed to user (Rule 14).
