# Web UI Refresh — Design Spec

**Status:** Accepted (user approval 2026-07-09; Autopilot granted through Steps 3–5)
**Branch:** `web-ui-refresh`
**Worktree:** `.worktree/web-ui-refresh`
**Owner:** solo developer

## 1. User-facing goal

Make the dashboard answer "what does my analyst believe today, and what changed?" at a
glance, and stop it reading as a generic blue admin template. Hackathon-polish quality:
sleek, minimalist, user-first. The signature element is **confidence in motion** —
before→after thesis deltas surfaced everywhere the data already exists.

## 2. Design direction (locked)

1. **Palette — ink on paper, color = meaning.** Near-monochrome (`#fbfbf9` bg, `#17181c`
   ink). Hue is reserved for semantics only: one rising tone (teal `#0f766e`) for
   confidence-up / delivered / ok; one falling tone (rust `#b3492b`) for confidence-down /
   undelivered / error. The default blue accent is removed; links and active nav are
   ink-weight, not blue.
2. **Type — data in mono.** UI stays system sans. Every numeric figure (confidence,
   scores, dates, counts) renders in a monospace stack with
   `font-variant-numeric: tabular-nums`, right-aligned in tables. System mono stack only
   (`ui-monospace, "SF Mono", "Cascadia Mono", Consolas, monospace`); no font files, no
   external requests (loopback tool).
3. **Signature — delta chips.** A shared visual for confidence change:
   `0.55 → 0.68 ▲` (rising tone) / `▼` (falling tone), used on Today, topic, and thesis
   pages.
4. **Dark mode** via `prefers-color-scheme: dark` on the existing CSS custom properties.
5. **Motion:** exactly one orchestrated moment — a staggered fade-up of the Today changes
   strip on load — wrapped in `prefers-reduced-motion: no-preference`. Nothing else
   animates beyond existing hovers.

## 3. Scope

| # | Change | Files |
|---|---|---|
| S1 | Token/palette rewrite, dark mode, mono numerals, numeric right-align, nav overflow fix, button/badge restyle | `web/static/app.css`, `templates/base.html` |
| S2 | Dossiers render as markdown (not `<pre>`) on topic + reading pages, reusing the report markdown path exposed as a Jinja filter | `web/app.py`, `templates/topic.html`, `templates/reading.html` |
| S3 | Today "what changed" strip above the report: thesis deltas for the latest report date (delta chips, per topic), count of new observations that day, `nothing_significant` topics as one quiet line each; report body below | `web/queries.py`, `web/app.py`, `templates/today.html`, `web/static/app.css` |
| S4 | Thesis page: confidence timeline as an inline SVG step chart built from `thesis_updates` (server-side points helper, no JS/chart lib); history table stays below | `web/queries.py` or template macro, `templates/thesis.html` |
| S5 | Topics index: add last-dossier-update, top thesis statement with confidence bar, and today's update count per row | `web/queries.py`, `templates/topics.html` |
| S6 | Ops: run state as a status pill (pulse while running), trigger buttons disabled while running, show `started_at`/`finished_at` from `run_status()` | `templates/ops.html`, `web/static/app.css` |
| S7 | Hygiene: actionable empty states (link to Ops), `target="_blank" rel="noopener"` on external item links, "Reading mode" → "Reading view" toggle styling | all templates |
| S8 | Test enablement: restore the missing `client` fixture (Flask `test_client` over `create_app` on a seeded temp DB) so `tests/test_web_routes.py` collects | `tests/conftest.py` |

## 4. Non-goals

- The `Nexus/` React app (untracked, separate product surface).
- Chart libraries, JS frameworks, webfont files, any external asset (CSP/loopback).
- Schema changes, new analyst/model calls, changes to pipeline or delivery code.
- Fixing the 4 non-web test collection errors (pre-existing debt, tracked separately).

## 5. Architecture and boundaries

- All new SELECTs live in `web/queries.py` (existing convention: read-only view-model
  builders). No writes anywhere in this feature.
- `render_report_html` becomes a module-level helper registered as a Jinja filter
  (`| markdown`) so dossiers and reports share one rendering path.
- SVG timeline: a pure function `confidence_points(updates) -> str` producing polyline
  coordinates; template owns the `<svg>` wrapper. No client-side JS.
- Today's deltas query: `thesis_updates` joined to `theses`/`topics`, filtered to
  `date(created_at) = <latest report_date>`. Topics present in the report with no
  updates/observations that day are the `nothing_significant` lines.

## 6. Data model / migration impact

None. Read-only queries over existing tables (`thesis_updates`, `theses`, `topics`,
`dossiers`, `observations`, `reports`).

## 7. Validation plan

- `ruff check src` + `ruff format` + `python -m compileall src` (CI gate parity).
- `pytest tests/test_web_routes.py tests/test_web_queries.py` green after S8, extended
  with: every route 200s on a seeded DB, deltas strip content, SVG points helper, and
  markdown filter output.
- Live smoke: `serve_dashboard` against a seeded temp DB + `curl` of every route
  (insight 2026-07-09: verify UI by driving it, not by reading templates).
- Visual check of light + dark rendering before PR.

## 8. Unresolved questions

None blocking.

## 9. Core invariant check

No analyst calls added (inv. 1); no memory-write paths touched (inv. 2, 3, 5);
`nothing_significant` is surfaced as a first-class UI element (inv. 4); no secrets
rendered or logged (inv. 7); justification per inv. 6: this feature makes the analyst's
*existing* reasoning legible — it adds no reasoning cost.
