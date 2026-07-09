# Web UI Redesign — Dark Terminal Dashboard

**Status:** Accepted (user-directed 2026-07-09: "Implement the redesign as faithfully as you can"; autonomous remote session — implementation authority granted in the session request)
**Branch:** `claude/web-ui-redesign-vfwtlg`
**Design authority:** [docs/ui-design.md](../ui-design.md) (v1.0 concept) + reference screenshot supplied in session
**Supersedes:** the "ink on paper" direction of `2026-07-09-web-ui-refresh.md` — the user judged the current UI "unserviceable as the final product."

## 1. User-facing goal

Replace the current light minimal dashboard with the dark, terminal-density briefing UI
specified in `docs/ui-design.md`: sidebar + top bar frame, Daily Briefing hero with four
KPI cards, and a three-column module grid (Story Timeline + Top Topics · Signal Intensity
chart + Hypotheses/Predictions · Recent Sources + Memory & Insights). Every module reads
from the SQLite store; every module links to a full section page. The implementation
should reflect the final product.

## 2. Data reality (constraint accepted by user)

No API keys are available in this session, so the analyst pipeline cannot ingest real
data. Per explicit user instruction ("Never mind the real data… Use mocks then"), a
deterministic seed script populates `data/analyst.db` with a realistic 90-day dataset.
All dashboard queries are real SQL over the real schema — the seed is the only mock.
When the pipeline later runs for real, the UI needs no changes.

## 3. Scope

| # | Task | Files |
|---|---|---|
| T1 | `horizon` column on `theses` (nullable TEXT, idempotent migration) + deterministic demo-seed script: 4 topics, ~10 sources, 90 days of items with daily-volume shapes, observations, 6 theses with `thesis_updates` history, dossiers, daily reports | `store/db.py`, `scripts/seed_demo_data.py` |
| T2 | Dashboard view-model queries: KPI aggregates (7d vs prev-7d + daily series), story timeline, per-topic daily signal series (90d), top-topics scores/trends, predictions table (status/band derivation), recent sources (domain + type badge), memory insights (entity/theme counts), briefing summary | `web/queries.py` (new `dashboard` section) |
| T3 | Design system: new `base.html` (sidebar nav ×7, system-status card, collapse; top bar with search/date-range/bell/identity) + full `app.css` rewrite to the `ui-design.md` token set (dark only) | `web/templates/base.html`, `web/static/app.css` |
| T4 | Dashboard page: hero briefing + 4 KPI cards (server-rendered SVG sparklines), signal chart (vanilla JS over embedded JSON: smooth bezier series, 7D/30D/90D toggle, hover crosshair + tooltip, legend series toggle), timeline, top topics, predictions, sources, memory modules | `web/templates/dashboard.html`, `web/static/dashboard.js`, `web/app.py` |
| T5 | Section pages restyled to the same system: Topics (card grid), Topic detail, Thesis detail, Sources (feed + health), Memory (dossiers + entities/themes), Reports (list + detail), Predictions (full table), Settings (ops + run controls) | all remaining templates, `web/app.py` |
| T6 | Route map: `/` → dashboard; `/sources` (alias `/items`), `/memory` (replaces `/reading`), `/predictions`, `/settings` (alias `/ops`); reading-mode cookie redirect removed; web tests updated to new routes/fixtures | `web/app.py`, `tests/conftest.py`, `tests/test_web_routes.py`, `tests/test_web_queries.py` |
| T7 | Validation: compileall + ruff (CI gate), web pytest, live serve + curl smoke on seeded DB, rendered-page screenshot check against the reference | — |

## 4. Non-goals

- No multi-agent/orchestration changes; UI + read-only queries only (Core Invariant 1 untouched).
- No entity-extraction subsystem: Key Entities are derived at query time from item titles (capitalized-token frequency), Recurring Themes from `observations.kind` counts. Good enough until a real extraction pass exists.
- The `Nexus/` React app is untouched.
- Light theme (explicit anti-goal in `ui-design.md`).
- Functional date-range picker/search/notifications: rendered faithfully as chrome; wiring them is backlog (logged in TODO.md).
- Repo test-suite collection rot outside web tests (pre-existing, already in TODO.md).

## 5. Derivations (data → design vocabulary)

- **KPI cards:** Sources Ingested = items count; New Events = observations count; Active Topics = active topics (+created in window); Confidence Shift = Σ(confidence_after − confidence_before) over window. All with prev-window delta + daily sparkline.
- **Prediction status pill:** Confirmed if confidence ≥ 0.8; Rising/falling from last-two-updates trajectory (falling → Watch); else Stable. Band: ≥0.7 High, ≥0.45 Medium, else Low.
- **Signal intensity:** per-topic daily item counts over 90d, scaled to 0–100 against the window max.
- **Topic score:** scaled 7d activity; rank arrow = vs previous 7d.
- **Source type badge:** domain/type heuristic (arxiv/anthropic → Paper, substack/newsletter → Newsletter, else Article).
- **Next brief countdown:** next 07:00 UTC after now, client-side tick.

## 6. Validation plan

`python -m compileall src`, `ruff check src` (CI gate), `ruff format`, targeted
`pytest tests/test_web_*`, live `create_app` serve over the seeded DB with curl smoke of
every route, and a Playwright screenshot of the dashboard compared against the reference
image.

## 7. Unresolved questions

None blocking. Grok CLI and GitNexus MCP are unavailable in this environment — recorded
fallbacks: senior-direct implementation, direct source reads.
