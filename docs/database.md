# Database and Persistence

## Storage Backend

SQLite, single file: `data/analyst.db`. Zero ops, easy backup (copy the file). Python's built-in `sqlite3` module. FTS5 extension for keyword search (bundled with SQLite ≥3.9).

## Schema

Full DDL lives in `store/db.py` → `init_db()`. Schema is reproduced here for reference.

### `users`

Single-user now; the table exists for future multi-user support. Code assumes one user.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `telegram_chat_id` | TEXT | For delivery |
| `created_at` | TEXT | datetime('now') |

### `topics`

What the analyst tracks.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `user_id` | INTEGER FK → users | |
| `slug` | TEXT UNIQUE | e.g. `ai-frontier-labs` |
| `name` | TEXT | Display name |
| `brief` | TEXT | What the user cares about; seeds the dossier |
| `active` | INTEGER | 1 = active |
| `created_at` | TEXT | |

### `sources`

RSS feeds, inbox folders, web pages.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `type` | TEXT | `rss` \| `inbox` \| `web`; future: `youtube`, `github` |
| `url` | TEXT | |
| `name` | TEXT | |
| `active` | INTEGER | |
| `last_fetched_at` | TEXT | |
| `fetch_error_count` | INTEGER | |
| `quality_score` | REAL | Phase 5: computed by `compute_source_quality` — `0.5*hit_rate + 0.5*citation_rate` |
| `status` | TEXT | Phase 5: `'active'` \| `'probation'`; DEFAULT `'active'`. New sources added via `analyst source add` start in `'probation'`. |
| `probation_until` | TEXT | Phase 5: ISO date; set to `now + 21 days` when a source is added. `transition_probation()` promotes to `'active'` once the date passes. |
| `created_at` | TEXT | |

**Probation lifecycle:** `analyst source add` sets `status='probation'` and `probation_until = today + 21 days`. The weekly run calls `transition_probation(conn)` which sets `status='active'` for any source past its `probation_until`. Quality scoring excludes probation sources from `bottom_decile` drop candidates.

**Migration:** `_ensure_columns(conn)` in `store/db.py` adds `status` and `probation_until` to pre-Phase-5 databases using `PRAGMA table_info` to check for the columns before issuing `ALTER TABLE`. It is safe to call on any database version.

### `topic_sources`

Many-to-many join between topics and sources. Sources can be shared across topics.

| Field | Type | Notes |
|---|---|---|
| `topic_id` | INTEGER FK → topics | |
| `source_id` | INTEGER FK → sources | |
| PK | `(topic_id, source_id)` | |

### `items`

Fetched documents. The analyst's raw material.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `source_id` | INTEGER FK → sources | |
| `url` | TEXT | |
| `content_hash` | TEXT UNIQUE | SHA-256 of extracted text; **the dedupe key** |
| `title` | TEXT | |
| `author` | TEXT | |
| `published_at` | TEXT | |
| `fetched_at` | TEXT | datetime('now') |
| `raw_text` | TEXT | Clean extracted text |
| `triage_summary` | TEXT | Haiku 2-liner |
| `triage_score` | REAL | 0–1 relevance from triage |
| `status` | TEXT | `new` \| `analyzed` \| `skipped` |

**FTS virtual table:**
```sql
CREATE VIRTUAL TABLE items_fts USING fts5(title, raw_text, content='items', content_rowid='id');
```
Sync triggers (`items_fts_ai`, `items_fts_au`, `items_fts_ad`) are created by `init_db()` to keep `items_fts` in sync with `items` on INSERT, UPDATE, and DELETE.

### `chunks`

Only created when/if vector retrieval is enabled (Phase 2+). Not used in V1.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `item_id` | INTEGER FK → items | |
| `chunk_index` | INTEGER | |
| `text` | TEXT | |
| `embedding` | BLOB | Or a sqlite-vec virtual table keyed by chunk id |

### `dossiers` — Analyst Memory Tier 1

One living document per topic. Permanent; rewritten by the analyst.

| Field | Type | Notes |
|---|---|---|
| `topic_id` | INTEGER PK FK → topics | One dossier per topic |
| `content` | TEXT | Markdown; analyst-maintained; ~1–2K token budget |
| `updated_at` | TEXT | |

### `theses` — Analyst Memory Tier 2

Analyst's active positions on a topic. **≤7 active per topic.**

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `topic_id` | INTEGER FK → topics | |
| `statement` | TEXT | e.g. `Open-weight models will reach frontier parity within 12 months` |
| `rationale` | TEXT | |
| `confidence` | REAL | 0–1, analyst-assessed |
| `status` | TEXT | `active` \| `confirmed` \| `revised` \| `retired` |
| `created_at` | TEXT | |
| `updated_at` | TEXT | |

### `thesis_updates` — Audit Trail

Every revision to a thesis writes one row here. Theses are **never silently edited.**

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `thesis_id` | INTEGER FK → theses | |
| `change` | TEXT | What changed and why |
| `confidence_before` | REAL | |
| `confidence_after` | REAL | |
| `triggered_by_item_id` | INTEGER FK → items | |
| `created_at` | TEXT | |

### `observations` — Analyst Memory Tier 3

Working memory. Append-only; expires on TTL unless promoted.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `topic_id` | INTEGER FK → topics | |
| `kind` | TEXT | `fact` \| `signal` \| `pattern` \| `contradiction` \| `question` |
| `content` | TEXT | |
| `importance` | INTEGER | 1 minor / 2 notable / 3 significant |
| `source_item_ids` | TEXT | JSON array of item IDs (citation trail) |
| `status` | TEXT | `active` \| `promoted` \| `expired` |
| `created_at` | TEXT | |

**FTS virtual table:**
```sql
CREATE VIRTUAL TABLE observations_fts USING fts5(content, content='observations', content_rowid='id');
```
Sync triggers (`observations_fts_ai`, `observations_fts_au`, `observations_fts_ad`) are created by `init_db()` alongside the `items_fts` triggers.

**TTL rules (Phase 4 compaction):**
- importance 1 → expires after 30 days
- importance 2 → expires after 90 days
- importance 3 → never auto-expires; must be explicitly retired or promoted

### `reports`

Stored verbatim. Is part of tomorrow's analyst context.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `user_id` | INTEGER FK → users | Always 1 — single-user MVP |
| `report_date` | TEXT UNIQUE | YYYY-MM-DD |
| `digest_text` | TEXT | What went to Telegram (HTML, ≤3,000 chars, unclosed tags stripped) |
| `full_markdown` | TEXT | Full report |
| `delivered_at` | TEXT | NULL until Telegram send succeeds |
| `created_at` | TEXT | |

### `citations` — Phase 5

Records which items were cited in each daily report. Written by `_record_citations` in `report/assemble.py` after assembly. Idempotent via `INSERT OR IGNORE`.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `report_id` | INTEGER FK → reports | |
| `report_date` | TEXT | YYYY-MM-DD; denormalized for fast range queries |
| `item_id` | INTEGER FK → items | |
| `source_id` | INTEGER FK → sources | resolved from `items.source_id` at write time |
| `created_at` | TEXT | |
| UNIQUE | `(report_id, item_id)` | prevents double-counting on re-run |

Used by `compute_source_quality` to compute per-source citation rates.

### `source_candidates` — Phase 5

Proposed sources returned by weekly discovery. Humans review and approve; nothing is auto-added.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `topic_id` | INTEGER FK → topics | |
| `url` | TEXT | |
| `domain` | TEXT | extracted from URL |
| `rationale` | TEXT | model's reason for suggesting this source |
| `status` | TEXT | `'pending'` \| `'approved'` \| `'rejected'`; DEFAULT `'pending'` |
| `created_at` | TEXT | |
| UNIQUE | `(topic_id, url)` | prevents duplicate proposals across weekly runs |

Approval UI is deferred to a future Web UI session. `analyst source candidates [--topic <slug>]` lists pending rows read-only.

## Memory Tier Summary

| Tier | Table | Lifetime | Budget | Written by |
|---|---|---|---|---|
| Dossier (durable understanding) | `dossiers` | Permanent, rewritten | ~1.5K tokens | Daily analyst (edits) + weekly compaction (full rewrite + appended self-review note) |
| Theses (positions) | `theses` + `thesis_updates` | Until retired | ≤7 active per topic | Daily analyst only, with audit trail; weekly run never edits theses |
| Observations (working memory) | `observations` | 30–90 days unless promoted; rows never deleted | ~3K tokens injected per run | Daily analyst (append); weekly compaction (`expire_observations` → `expired`; `apply_weekly_review` → `promoted`) |

## Migration Rules

- Migrations are applied by `init_db()` using `CREATE TABLE IF NOT EXISTS` for all tables.
- Schema changes require a version bump and a `migrate_vN()` function called by `init_db()`.
- Column additions to existing tables use `_ensure_columns(conn)` with `PRAGMA table_info` guards — idempotent, safe on any database age. Phase 5 uses this pattern for `sources.status` and `sources.probation_until`.
- Backward compatibility must be explicit.
- Data deletion must be intentional and documented.
- Tests must cover migration-sensitive behavior.
- Never drop columns or tables without explicit user approval.

## State Ownership

| State | Module that owns writes |
|---|---|
| `items` inserts | `ingestion/` modules via `store.db.insert_item()` — never bare INSERT |
| `items.triage_*`, `items.status` | `analyst/triage.py` — UPDATEs only; caller owns `conn.commit()` |
| `dossiers`, `observations`, `theses`, `thesis_updates` | `analyst/memory.py` via `apply_all_memory_writes()` — single `with conn:` transaction after daily agent call |
| `observations.status` (expiry), `dossiers` (rewrite + note), `observations.status` (promotion) | `analyst/compaction.py` — `expire_observations()` commits separately (idempotent SQL); `apply_weekly_review()` writes dossier rewrite + promoted IDs in one `with conn:` transaction |
| `reports` | `report/assemble.py` — upserts on `report_date` conflict; `user_id` always 1 |
| `reports.delivered_at` | `delivery/telegram.py` — set only on confirmed Telegram success |
| `citations` | `report/assemble.py` via `_record_citations()` — INSERT OR IGNORE after assembly |
| `source_candidates` | `analyst/discovery.py` via `discover_sources()` — INSERT OR IGNORE; status only changed by future approval UI |
| `sources.quality_score` | `quality.py` via `compute_source_quality()` — pure SQL UPDATE, run weekly |
| `sources.status`, `sources.probation_until` | `cli.py` (`analyst source add` writes initial values); `quality.py` (`transition_probation` clears probation) |
| `sources.last_fetched_at`, `sources.fetch_error_count` | `ingestion/rss.py` |
| `sources` (inbox) inserts | `ingestion/inbox.py` via `get_or_create_inbox_source()` — canonical helper; never duplicated inline |

## Persistence Invariants

- `content_hash` is the authoritative dedupe key for items. Duplicate inserts silently skip (`INSERT OR IGNORE`).
- All analyst memory writes (observations + thesis updates + dossier edit) must be atomic — one transaction.
- `thesis_updates` rows are immutable — never update or delete them.
- `observations` rows are append-only — never update them; only change `status`.
- `delivered_at` is set only on confirmed Telegram success.
