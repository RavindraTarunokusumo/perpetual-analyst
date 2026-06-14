# Web UI Dashboard — Design

**Date:** 2026-06-14
**Status:** Approved (brainstorm)
**Scope:** Out of SPEC v1; a local single-user dashboard over the existing SQLite data.

## Goal

A local, single-user web dashboard that unifies three jobs over the existing
`data/analyst.db`:

1. **Reading** — browse today's report and the archive; drill from a report into
   the topics, theses, observations, and items behind it.
2. **Memory inspection** — see what the analyst "knows": per-topic dossier,
   active theses with confidence history (the `thesis_updates` audit trail), and
   observations with their citation trails.
3. **Operations** — source fetch health, ingest/triage stats, and three light
   write actions.

It is read-mostly. It adds exactly three mutations, each routed through an
existing guarded code path — never bare SQL. It does **not** edit theses, so
Invariant 3 ("theses are never silently edited") is untouched by the UI.

## Non-Goals

- No authentication, no multi-user, no remote exposure. Binds `127.0.0.1`.
- No thesis editing/retiring from the UI (deferred — it would require writing a
  `thesis_updates` audit row and is the heaviest action to do correctly).
- No new analytics, charts library, or build toolchain. Server-rendered HTML,
  one hand-written stylesheet.
- No new data model. The UI reads the schema in `store/db.py` as-is.

## Stack

Flask + Jinja2, server-rendered. Rationale: it is a local single-user
read-oriented tool; server-rendered HTML needs no build step and the same Python
process imports the existing `store/`, `report/`, `delivery/`, and `daily_run`
modules directly. New runtime dependencies: `flask`. No JS framework; a few lines
of vanilla JS only for the run-status poll.

## Architecture

New package `src/perpetual_analyst/web/`:

```
web/
  __init__.py
  app.py          # create_app(db_path) factory; thin route handlers
  queries.py      # read-only view-model builders — all SELECTs live here
  actions.py      # the 3 write handlers + run lock + background-run thread
  templates/      # base.html + one template per page (Jinja)
  static/app.css  # one stylesheet, no build step
```

**Layering / boundaries:**

- `queries.py` — pure functions `(conn, ...) -> dict | list[dict]`. All SQL is
  here. Each builds a plain view-model the templates render dumbly. Testable in
  isolation against a seeded in-memory DB.
- `actions.py` — the three POST handlers and the run orchestration (module-level
  lock + status dict + background thread). Reuses existing module functions.
- `app.py` — `create_app(db_path)` Flask factory. Route handlers are thin: open a
  request-scoped connection, call a `queries.py` builder, `render_template`.
  Registers the `actions.py` handlers. No SQL in `app.py`.
- Templates: `base.html` provides the nav + the global Reading-mode switch +
  flash messages; one focused template per page.

**Connection handling:** read routes open a short-lived `sqlite3` connection per
request (`row_factory = Row`, `PRAGMA foreign_keys = ON`) and close it in
`teardown`. The background daily-run thread opens its **own** connection (SQLite
connections are not shareable across threads). WAL mode (already set by
`init_db`) lets request reads proceed alongside a running daily job.

**CLI:** a new `analyst web` command in `cli.py`:

```
analyst web --host 127.0.0.1 --port 8080 --db-path data/analyst.db
```

It calls `create_app(db_path).run(host, port)`. Defaults bind loopback only.

## Pages (read)

| Route | Page | Contents |
|---|---|---|
| `/` | **Today** | Latest `reports` row: digest + full markdown (rendered); links into topics. Empty state if no report yet. |
| `/topics` | **Topics** | List of active topics with counts (theses, recent items). |
| `/topics/<slug>` | **Topic** (full) | Dossier; active theses (latest confidence + bar); recent observations (kind, importance, citation trail); sidebar: recent items (triage score/status) + source health. |
| `/topics/<slug>/thesis/<id>` | **Thesis** | Statement, rationale, current confidence, and the full `thesis_updates` history (confidence before→after, change reason, triggering item). |
| `/reports` | **Reports** | Archive by `report_date`; undelivered ones flagged with a retry control. |
| `/reports/<date>` | **Report** | Full stored markdown for a date. |
| `/items` | **Items** | Ingested feed: title, source, triage score/summary, status. Filter by source and status. Hosts the add-inbox form. |
| `/ops` | **Ops** | Sources table (last_fetched_at, fetch_error_count, active); ingest/triage counts; the trigger-run control + live status. |
| `/reading` | **Reading mode** | Stacked list of every topic's dossier — a quiet, full-width reading surface. |

**Global Reading mode:** the nav holds a Reading switch backed by a cookie. When
on, the nav highlights it and the user lands on `/reading` (all dossiers stacked,
each linking to its full Topic page). Turning it off returns to the normal
dashboard. It is an alternate full-surface view, not a per-topic toggle.

**Empty states:** every read page renders a calm empty state on sparse data
("No report yet — run the pipeline.", "No active theses.", "No items ingested.")
and never 500s.

## Write actions (3)

All POST, all reuse existing guarded paths; each flashes a result and redirects
back.

1. **Trigger run** — `POST /actions/run` (optional `dry_run`). Spawns a daemon
   thread that builds its own `conn` + client + settings and calls
   `daily_run.run_daily(...)` (reusing `make_client`, `load_settings`,
   `force_utf8_stdout`). A module-level lock + status dict
   (`{state, started_at, finished_at, error}`) allows only **one** run at a time;
   a second request while running is rejected with a flash. `/ops` shows the
   status, refreshed by a small JS poll of `GET /actions/run/status` (JSON).

2. **Retry undelivered** — `POST /actions/retry` → `delivery.telegram.retry_undelivered(...)`.
   The control is disabled with an explanatory note when Telegram credentials are
   absent in settings.

3. **Add inbox item** — `POST /actions/inbox` with `url` and/or `text`. Resolves
   the `inbox` source id, computes the content hash the ingestion path uses, and
   calls `store.db.insert_item(...)`. Dedupe is silent (Invariant 8). The item is
   picked up by the next run's triage.

## Error handling & invariants

- **Invariant 7 (secret hygiene):** the UI never renders or logs
  `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` / `TELEGRAM_BOT_TOKEN`. Action
  handlers catch exceptions and flash **`type(exc).__name__` only** — never the
  message (which can echo a URL with a token).
- **Invariant 3 (theses):** the UI performs no thesis writes at all.
- **Invariant 5/8:** the only writes are `insert_item` (silent-dedupe) and the
  run/retry paths, which own their own transactions. No bare SQL writes.
- Single-user assumption (`user_id = 1`) preserved.
- Concurrency: one run at a time (lock); request reads are independent
  connections; WAL permits concurrent read + the run's writes.

## Testing

- Flask **test client** against an in-memory DB seeded by a fixture (topics,
  sources, items at each status, dossier, theses + updates, observations, a
  delivered and an undelivered report).
- `queries.py` builders unit-tested directly (seeded DB → expected view-model).
- **Read routes:** each GET returns 200 and shows seeded content; each also
  renders its empty state on an empty DB.
- **Actions:**
  - inbox → real `insert_item`, asserts the row and silent re-post dedupe.
  - run → `run_daily` monkeypatched at the boundary; asserts it is invoked in a
    thread and that a concurrent second request is rejected by the lock.
  - retry → `retry_undelivered` monkeypatched; asserts called, and that the
    control is disabled when creds are absent.
  - Reading-mode cookie toggle changes the rendered surface.
- No live API in the unit suite.
- **Bounded live validation (required, per workflow):** launch `analyst web`
  against the real `data/analyst.db`, click through every page, exercise
  add-inbox, and trigger a `--dry-run` run from `/ops`. This touches IO/network,
  which mocks cannot cover.

## File-size / focus notes

Splitting SQL (`queries.py`), write/orchestration (`actions.py`), and routing
(`app.py`) keeps each file single-purpose and within easy reading size. Templates
are one-per-page so no single template grows tangled.
