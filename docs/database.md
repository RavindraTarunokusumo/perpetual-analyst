# Database and Persistence

## Two-Database Topology

PA uses **two datastores**:

| Store | Engine | Location | Purpose |
|---|---|---|---|
| **Operational** | SQLite | `data/analyst.db` | Topics, sources, items, reports, delivery, weekly-subsystem tables |
| **Memory** | Postgres + pgvector | `DATABASE_URL` in `Nexus/.env` | Corpus (`documents`/`spans`) + analytical memory objects |

`perpetual_analyst/substrate.py` is the **only** PA module that writes to or reads from Postgres.
SQLite migrations live in `store/db.py` → `init_db()`. Postgres migrations live in the Nexus
submodule: `Nexus/app/db/migrations/` (Alembic). Run `alembic upgrade head` from the Nexus tree
with `DATABASE_URL` set.

Daily retrieval is **not** FTS5. Corpus search uses Nexus sentence-window retrieval over
pgvector span embeddings (window=2, top_k=15, fetch_k=60, topic-scoped via `Document.scope`).

---

## SQLite — Operational Store

SQLite, single file: `data/analyst.db`. Easy backup (copy the file). Python's built-in `sqlite3`
module. FTS5 virtual tables may still exist in the schema for legacy weekly-subsystem tables
(`items_fts`, `observations_fts`) but are **not** used on the daily analyst path.

Full DDL lives in `store/db.py` → `init_db()`. Schema is reproduced here for reference.

### `users`

Single-user now; the table exists for future multi-user support. Code assumes one user.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `telegram_chat_id` | TEXT | For delivery |
| `created_at` | TEXT | datetime('now') |

### `topics`

What the analyst tracks. `slug` maps 1:1 to Postgres `watch_topics.slug` via `substrate.get_or_create_watch_topic`.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `user_id` | INTEGER FK → users | |
| `slug` | TEXT UNIQUE | e.g. `ai-frontier-labs` |
| `name` | TEXT | Display name |
| `brief` | TEXT | What the user cares about; seeds retrieval focus |
| `active` | INTEGER | 1 = active |
| `created_at` | TEXT | |

### `sources`

RSS feeds, inbox folders, web pages. Fetch lifecycle and quality scoring stay here; reliability profiles for daily analysis live in Postgres `source_profiles`.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `type` | TEXT | `rss` \| `inbox` \| `web`; future: `youtube`, `github` |
| `url` | TEXT | |
| `name` | TEXT | |
| `active` | INTEGER | |
| `last_fetched_at` | TEXT | |
| `fetch_error_count` | INTEGER | |
| `quality_score` | REAL | Computed by `compute_source_quality` — `0.35*hit_rate + 0.35*citation_rate + 0.15*uniqueness_rate + 0.15*freshness_lead_rate` |
| `status` | TEXT | `'active'` \| `'probation'`; DEFAULT `'active'`. New sources added via `analyst source add` start in `'probation'`. |
| `probation_until` | TEXT | ISO date; set to `now + 21 days` when a source is added. `transition_probation()` promotes to `'active'` once the date passes. |
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

Fetched documents. Raw material before corpus ingest. Item text is mirrored into Postgres `documents`/`spans` via `substrate.ingest`.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `source_id` | INTEGER FK → sources | |
| `url` | TEXT | |
| `content_hash` | TEXT UNIQUE | SHA-256 of extracted text; **the dedupe key** (SQLite side) |
| `title` | TEXT | |
| `author` | TEXT | |
| `published_at` | TEXT | |
| `fetched_at` | TEXT | datetime('now') |
| `raw_text` | TEXT | Clean extracted text |
| `triage_summary` | TEXT | Qwen flash 2-liner |
| `triage_score` | REAL | 0–1 relevance from triage |
| `status` | TEXT | `new` (freshly inserted) → `skipped` (triage score < 0.2) or → `analyzed` (written by `run_topic` inside the memory-write transaction) |

### `chunks`

Legacy table for the retired sqlite-vec path. Not used in the daily Nexus path.

### `dossiers` — Weekly Subsystem (SQLite legacy)

One living document per topic. Used by **weekly compaction** (`run_weekly_review`), not the daily narrative loop. The daily source of truth is Postgres `narrative_states`.

| Field | Type | Notes |
|---|---|---|
| `topic_id` | INTEGER PK FK → topics | One dossier per topic |
| `content` | TEXT | Markdown; rewritten by weekly review |
| `updated_at` | TEXT | |

### `theses` — Weekly Subsystem (SQLite legacy)

Analyst positions for the weekly review path. Daily competing hypotheses live in Postgres `hypotheses`.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `topic_id` | INTEGER FK → topics | |
| `statement` | TEXT | |
| `rationale` | TEXT | |
| `confidence` | REAL | 0–1 |
| `status` | TEXT | `active` \| `confirmed` \| `revised` \| `retired` |
| `created_at` | TEXT | |
| `updated_at` | TEXT | |

### `thesis_updates` — Weekly Audit Trail (SQLite legacy)

Every revision to a SQLite thesis writes one row here.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `thesis_id` | INTEGER FK → theses | |
| `change` | TEXT | What changed and why |
| `confidence_before` | REAL | |
| `confidence_after` | REAL | |
| `triggered_by_item_id` | INTEGER FK → items | |
| `created_at` | TEXT | |

### `observations` — Weekly Subsystem (SQLite legacy)

Working memory for weekly compaction. Daily claims/events live in Postgres.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `topic_id` | INTEGER FK → topics | |
| `kind` | TEXT | `fact` \| `signal` \| `pattern` \| `contradiction` \| `question` |
| `content` | TEXT | |
| `importance` | INTEGER | 1 minor / 2 notable / 3 significant |
| `source_item_ids` | TEXT | JSON array of item IDs |
| `status` | TEXT | `active` \| `promoted` \| `expired` |
| `created_at` | TEXT | |

**TTL rules (weekly compaction):**
- importance 1 → expires after 30 days
- importance 2 → expires after 90 days
- importance 3 → never auto-expires; must be explicitly retired or promoted

### `reports`

Stored verbatim. Is part of tomorrow's analyst context (digest lines).

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `user_id` | INTEGER FK → users | Always 1 — single-user MVP |
| `report_date` | TEXT UNIQUE | YYYY-MM-DD |
| `digest_text` | TEXT | What went to Telegram (HTML, ≤3,000 chars, unclosed tags stripped) |
| `full_markdown` | TEXT | Full report assembled from `NarrativeUpdate.briefing_markdown` |
| `delivered_at` | TEXT | NULL until Telegram send succeeds |
| `created_at` | TEXT | |

### `citations` — Legacy

Records which items were cited in historical reports (pre-Nexus citation path). The daily report no longer renders `[item:N]` tags; provenance lives in Postgres `claim_evidence`. The `citations` table may still exist for `compute_source_quality` on older report data.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `report_id` | INTEGER FK → reports | |
| `report_date` | TEXT | YYYY-MM-DD |
| `item_id` | INTEGER FK → items | |
| `source_id` | INTEGER FK → sources | |
| `created_at` | TEXT | |
| UNIQUE | `(report_id, item_id)` | |

### `source_candidates`

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
| `reviewed_at` | TEXT | set when approved or rejected |
| `review_note` | TEXT | optional operator note from the Web UI |
| UNIQUE | `(topic_id, url)` | prevents duplicate proposals across weekly runs |

`analyst source candidates [--topic <slug>]` lists rows read-only. The local
Web UI (`analyst web`) approves or dismisses candidates. Approval validates and
fetches only public HTTP(S) URLs before creating a probation source and linking
it to the candidate topic.

### `fts_insufficiencies`

Legacy gate for the retired sqlite-vec + Voyage embeddings path. Not used on the daily Nexus path.

---

## Postgres — Memory Store (Nexus)

Managed by Alembic in `Nexus/app/db/migrations/`. Key migrations for PA integration:
`0008_document_scope` (topic-scoped corpus), `0009_pa_analytical_tables`, `0010_claims_document_nullable`.

### Corpus tables

| Table | Purpose |
|---|---|
| `documents` | Ingested item text; `content_hash` dedupe; `scope` = PA topic slug for retrieval filter |
| `spans` | Sentence-level chunks with `embedding vector(384)` (BAAI/bge-small-en-v1.5) |

Ingest is zero-LLM: `ingest_sentence_spans` splits text, embeds locally, stores spans.

### Analytical tables (8 + watch_topics)

All scoped by `topic_id` (FK → `watch_topics`). PA theses map to `hypotheses`; dossier maps to latest `narrative_states`.

| Table | Purpose |
|---|---|
| `watch_topics` | Mirror of PA `topics.slug`; UUID primary key |
| `source_profiles` | Reliability/incentive notes per source (daily synthesis output) |
| `claims` | Source-backed assertions; `claim_evidence` links to `spans` |
| `claim_evidence` | `(claim_id, span_id, evidence_role, quote)` — provenance for inspector/Q&A |
| `events` | Time-stamped developments; `claim_ids` JSON references |
| `narrative_states` | **Source of truth** — versioned narrative with `change_summary`, `prev_version_id` |
| `hypotheses` | Competing interpretations; ≤7 active per topic; retired rows preserve history |
| `predictions` | Scored forecasts; `open` → `hit` / `miss` / `expired` via `resolve_lifecycle` |
| `user_preferences` | Optional framing/interests per topic (Nexus schema; not yet wired in PA MVP) |

`claims` and `claim_evidence` pre-existed in Nexus schema; PA extends `claims` with `topic_id` and `source_authority` (migration 0009).

---

## Memory Tier Summary

| Tier | Store | Table(s) | Lifetime | Written by |
|---|---|---|---|---|
| Narrative (durable understanding) | Postgres | `narrative_states` | Permanent, versioned | Daily `persist_bundle` |
| Hypotheses (positions) | Postgres | `hypotheses` | Until retired; ≤7 active | Daily `persist_bundle` (snapshot replace) |
| Claims + events (working facts) | Postgres | `claims`, `events` | Active → superseded/stale | Daily `persist_bundle` |
| Predictions | Postgres | `predictions` | Until resolved/expired | Daily `persist_bundle`; lifecycle via `analyst score` |
| Corpus (retrieval) | Postgres | `documents`, `spans` | Permanent | `substrate.ingest` (zero-LLM) |
| Dossier (weekly legacy) | SQLite | `dossiers` | Rewritten weekly | `apply_weekly_review` |
| Theses (weekly legacy) | SQLite | `theses` + `thesis_updates` | Until retired | Weekly review context only |
| Observations (weekly legacy) | SQLite | `observations` | 30–90 days unless promoted | Weekly compaction |

## Migration Rules

**SQLite:**
- Migrations are applied by `init_db()` using `CREATE TABLE IF NOT EXISTS` for all tables.
- Schema changes require a version bump and a `migrate_vN()` function called by `init_db()`.
- Column additions use `_ensure_columns(conn)` with `PRAGMA table_info` guards — idempotent.
- Never drop columns or tables without explicit user approval.

**Postgres:**
- Migrations are Alembic revisions in `Nexus/app/db/migrations/versions/`.
- Run from Nexus: `alembic upgrade head` with `DATABASE_URL` set.
- PA does not embed Postgres DDL in `store/db.py`.

## State Ownership

| State | Module that owns writes |
|---|---|
| `items` inserts | `ingestion/` modules via `store.db.insert_item()` — never bare INSERT |
| `items.triage_*`, `items.status` | `analyst/triage.py` — UPDATEs only; caller owns `conn.commit()` |
| Postgres corpus (`documents`, `spans`) | `substrate.ingest` — dedupe via `content_hash`; topic scope via `Document.scope` |
| Postgres analytical objects | `substrate.persist_bundle` — single async Postgres transaction after synthesis |
| `dossiers`, `observations`, `theses`, `thesis_updates` (weekly) | `analyst/memory.py` via `apply_weekly_review` / compaction — SQLite only |
| `reports` | `report/assemble.py` — upserts on `report_date` conflict; `user_id` always 1 |
| `reports.delivered_at` | `delivery/telegram.py` — set only on confirmed Telegram success |
| `source_candidates` | `analyst/discovery.py` inserts pending rows; `analyst/candidates.py` changes status on operator approval/dismissal |
| `sources.quality_score` | `quality.py` via `compute_source_quality()` — deterministic SQL/Python UPDATE, run weekly |
| `sources.status`, `sources.probation_until` | `cli.py` (`analyst source add` writes initial values); `quality.py` (`transition_probation` clears probation) |
| `sources.last_fetched_at`, `sources.fetch_error_count` | `ingestion/rss.py` |
| `sources` (inbox) inserts | `ingestion/inbox.py` via `get_or_create_inbox_source()` — canonical helper; never duplicated inline |
| `predictions` lifecycle, `claims` decay | `substrate.resolve_lifecycle` via `analyst score` CLI |

## Persistence Invariants

- `content_hash` is the authoritative dedupe key for items (SQLite) and documents (Postgres). Duplicate inserts silently skip.
- Daily analytical writes must be atomic within Postgres — one `persist_bundle` transaction.
- `nothing_significant: true` skips `persist_bundle` writes (no new narrative version).
- `delivered_at` is set only on confirmed Telegram success.
- Global `content_hash` dedupe in Postgres is cross-topic: a document has one `scope`; the same article ingested under two topics is stored once under whichever ingested first.