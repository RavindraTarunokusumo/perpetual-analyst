# 2026-07-09 — Web UI polish + dashboard run-blocker fixes

**Spec:** none (direct polish session; no formal `docs/specs/` entry). Scope agreed in-session: visual restyle + small UX fixes at "full refresh" depth, then fix the blockers preventing the dashboard from running.

**PR:** #11 · **Merge commit:** `f3eab3b`

## What shipped

Visual refresh of the local Flask dashboard and the fixes that make it actually launch again.

### UI polish
- [x] Rewrite `web/static/app.css` into a token-based design system (neutral ramp + single accent, cards, badges, focus rings, responsive `.table-wrap`, primary/secondary buttons) — `16e7ffc`
- [x] Apply the system across templates + fix the never-applied nav active-state (`request.endpoint`), wrap tables for mobile scroll, badges, %-width confidence bars, tidy Items form / Ops run controls — `4062a41`

### Run-blocker fixes (all pre-existing, from the Nexus refactor)
- [x] `analyst/triage.py`: close unterminated module docstring (SyntaxError) — `512abd1`
- [x] `cli.py`: close unterminated module docstring + remove shadowed dead duplicate `topic add`/`source add` block — `bdc0249`
- [x] `web/app.py` + `web/__init__.py`: drop dead `report.render` import (retired citation path), add missing `serve_dashboard()` entry point; remove orphaned `tests/test_render.py` — `512abd1` (test) / `627c1e3`
- [x] `web/actions.py`: reconcile run trigger to `daily_run.main()` (was importing removed `force_utf8_stdout`/`run_daily`) — `a5d8d2c`

## Validation
- ruff + ruff-format clean on all changed files; pre-commit (ruff hooks) passed on changed files.
- All 10 dashboard routes render HTTP 200 via Flask test client through the real `actions`/`daily_run` chain; live `serve_dashboard` smoke (curl `/topics`, `/ops` → 200); `analyst --help` registers all commands including `web`.
- `tests/test_triage.py` passes (5). Full `pytest` does **not** collect on `main` due to pre-existing refactor rot (see backlog).

## Discovered backlog (pre-existing, out of scope)
Test suite does not collect on `main`: `test_search` → deleted `retrieval` module, `test_smoke` → missing `agent.run_topic`, `test_web_actions` → removed `daily_run` symbols, `test_web_queries`/`test_web_routes` → removed `seeded_conn` fixture. Logged in `TODO.md`.
