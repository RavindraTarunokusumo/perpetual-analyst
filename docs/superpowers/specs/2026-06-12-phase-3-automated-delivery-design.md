# Phase 3 — Automated Delivery Design

**Date:** 2026-06-12
**Scope:** Tasks 9–10 from TODO.md (report assembly + rendering, Telegram delivery + scheduler + orchestrator) plus the Phase 2 handoff-note items
**Branch:** `phase-3-automated-delivery`

Second of three sub-projects in this session (Phase 2 ✅ → Phase 3 → Web UI).

---

## Decisions Locked In

| # | Decision | Choice |
|---|---|---|
| 1 | Digest generation | One additional LLM call per **day** (not per topic) on `settings.analyst.id`, structured output `DigestOutput {executive_summary: str, digest_text: str}` — explicitly sanctioned extension of Invariant 1 (user-approved 2026-06-12). No numeric Field bounds in the schema (provider rejects `minimum`/`maximum`; Phase 2 lesson) |
| 2 | Telegram credentials | `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` from env; when unset, delivery is **skipped with a warning** and the report remains stored (`delivered_at IS NULL`); `retry_undelivered()` delivers on a later run. All tests fully mocked; no live Telegram this phase |
| 3 | Scheduler | Document both Windows Task Scheduler (`schtasks`) and Linux cron in `docs/commands.md`; register neither |
| 4 | Per-day guard (Invariant 1) | `daily_run` skips triage+analysis+assembly when a `reports` row exists for today (`report_date = date('now')`); ingestion and delivery-retry still run |
| 5 | Item selection helper | `select_analyst_items(topic_id, conn, limit=10)` in `analyst/triage.py` (owns `SKIP_THRESHOLD`): `status='new' AND triage_score >= SKIP_THRESHOLD`, topic-scoped via `topic_sources`, ordered by score desc. Smoke test switches to it (fixes global selection) |
| 6 | Source reactivation | `sync_config` resets `fetch_error_count = 0` when a YAML-active source row was inactive in the DB (Phase 2 handoff note) |
| 7 | Orchestration shape | Plain function pipeline in `daily_run.py` with per-stage and per-topic try/except; failures collected and printed, never fatal to other stages/topics |
| 8 | Digest length guard | Telegram digest hard-truncated to 3,000 chars at the last paragraph boundary before send (structural guard, not prompt hope — Invariant 2 spirit) |

---

## Module Interfaces

### `analyst/schemas.py` (extend)

```python
class DigestOutput(BaseModel):
    executive_summary: str   # 3-6 sentences, cross-topic, for the report header
    digest_text: str         # <=3,000 chars, Telegram-ready, analyst's first-person voice
```

### `report/render.py` (Task 9a)

```python
def render_citations(markdown: str, conn: sqlite3.Connection) -> str
```
- Replaces each `[item:N]` with `[^k]` (stable numbering in order of first appearance) and appends a `## Sources reviewed` footnote list: `[^k]: {title} — {url}` from the `items` table.
- Unknown item ids render as plain `item:N` text (never raise). `[obs:N]`/`[thesis:N]` tags pass through untouched (internal memory references).

### `report/assemble.py` (Task 9b)

```python
def assemble_report(
    topic_results: list[tuple[Topic, TopicAnalysis]],
    conn: sqlite3.Connection,
    client: openai.OpenAI,
    settings: Settings,
    report_date: str,
) -> tuple[str, str]   # (digest_text, full_markdown)
```
- Builds the SPEC §9 template: exec summary (from digest call) → per-topic sections (`report_section_markdown`; `nothing_significant` topics get one line: `*{name}: nothing significant today.*`) → merged Open questions → merged Things to watch next → footnotes via `render_citations`. Empty sections omitted.
- Digest call: system prompt `analyst/prompts/digest.md`, user content = concatenated topic sections + thesis-update fragments; `client.beta.chat.completions.parse(..., response_format=DigestOutput)`; parsed via `response.choices[0].message.parsed`.
- Digest-call failure → fallback: exec summary omitted, digest = first 3,000 chars of the topic sections (delivery still possible); failure printed.

```python
def persist_report(report_date, digest_text, full_markdown, conn) -> int
```
- Plain `INSERT` into `reports` — UNIQUE `report_date` raises on a duplicate by design (the per-day guard prevents reaching here twice; a raise here means the guard was bypassed and should be loud). Also writes `data/reports/brief-{report_date}.md`.

### `analyst/prompts/digest.md` (Task 9c)

Encodes SPEC §10 voice rules: first person, confident, terse; 🎯 exec summary → top 3 developments (one line + why each) → thesis changes if any → watch next; ≤3,000 chars; no per-topic exhaustiveness.

### `delivery/telegram.py` (Task 10a)

```python
def send_report(report: Report, conn: sqlite3.Connection) -> bool
def retry_undelivered(conn: sqlite3.Connection) -> int   # count delivered
```
- Env-gated: missing token/chat-id → print warning, return False (report stays undelivered).
- `send_report`: HTML-parse-mode digest message (truncated per Decision 8) + full markdown attached via `send_document` (filename `brief-{report_date}.md`). On success stamp `delivered_at = datetime('now')`. python-telegram-bot async API wrapped with `asyncio.run`.
- Send failure → print error (no token in output — Invariant 7), return False; row remains `delivered_at IS NULL`.
- `retry_undelivered`: `SELECT * FROM reports WHERE delivered_at IS NULL ORDER BY report_date` → `send_report` each.

### `analyst/triage.py` (extend — Decision 5)

```python
def select_analyst_items(topic_id: int, conn: sqlite3.Connection, limit: int = 10) -> list[Item]
```

### `config.py` (extend — Decision 6)

In `sync_config`'s source-UPDATE branch: when the existing row has `active = 0` and the YAML entry is active, also set `fetch_error_count = 0`.

### `daily_run.py` (Task 10b)

```python
def run_daily(conn, client, settings, topic_slug: str | None = None, dry_run: bool = False) -> None
def main() -> None   # entry point: python -m perpetual_analyst.daily_run
```
Pipeline (each stage in try/except; per-topic loops also per-iteration try/except):
1. `sync_config(conn, load_topics(), load_sources())`
2. Ingest: `scan_inbox` per active topic with an inbox source; `fetch_rss` per active rss source
3. Per-day guard: if `reports` row for today exists → skip 4–6, go to 7
4. Triage per topic: untriaged items for the topic (`status='new' AND triage_score IS NULL`, joined via `topic_sources`) through `triage_items`, then `select_analyst_items`
5. Analyst per topic: `run_topic(...)`. With `dry_run=True`, stages 1–5 run with prompts printed (zero API calls) and stages 6–7 are skipped
6. Assemble + persist: `assemble_report` → `persist_report`
7. Deliver: `retry_undelivered(conn)`
- `--topic` filters stages 4–5 to one topic (assembly still includes only produced results).
- Stage failures print `[daily] stage X failed: ...` and continue to the next stage where meaningful (a failed assemble skips persist; delivery retry always runs).

### `cli.py` (extend)

`analyst run [--topic SLUG] [--dry-run] [--db-path PATH]` → `run_daily`. Replaces the `NotImplementedError` stub.

### `docs/commands.md` (Task 10c)

- Windows: `schtasks /Create /SC DAILY /ST 06:30 /TN PerpetualAnalyst /TR "<venv-python> -m perpetual_analyst.daily_run"` (working-directory caveat documented)
- Linux: `30 6 * * * cd /path/to/perpetual-analyst && .venv/bin/python -m perpetual_analyst.daily_run`

---

## Error Handling Summary

| Failure | Behavior |
|---|---|
| Digest LLM call fails | Mechanical fallback digest; exec summary omitted; run continues |
| Telegram env unset | Warning printed; report stored undelivered; retried when credentials appear |
| Telegram send fails | Report stays `delivered_at IS NULL`; next run retries (SPEC §10) |
| One topic's triage/analysis fails | Other topics proceed; failed topic absent from today's report |
| Duplicate daily run | Per-day guard skips analysis; only delivery retry executes |
| Unknown `[item:N]` citation | Rendered as plain text, never raises |

## Testing

All mocked (no live API/Telegram):
- render: footnote numbering/order, unknown ids, obs/thesis tags untouched, sources list content
- assemble: section merging, nothing_significant one-liner, omitted-when-empty, digest mock plumbed, digest-failure fallback, persist writes row + file (tmp_path)
- telegram: mocked Bot — success stamps delivered_at, failure leaves NULL, retry delivers backlog, env-unset skips without raising, token never in printed output
- triage: select_analyst_items topic scoping (two topics, crossed sources), threshold and limit
- config: reactivation resets fetch_error_count
- daily_run: full pipeline with mocked client + mocked fetchers — per-stage isolation (poisoned topic doesn't kill run), per-day guard, --topic filter, dry-run makes zero API calls
- smoke test updated to use `select_analyst_items` (still `-m smoke`, not run this phase)

Manual validation: `analyst run --dry-run` end-to-end on the real DB/config (no API cost).

## Out of Scope

- Web UI → next sub-project
- Live Telegram delivery (credentials later), weekly compaction, prompt caching → Phase 4+
- Live analyst/digest runs (OpenRouter balance pending top-up)
