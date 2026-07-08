# PA ↔ Nexus Integration — Lightweight Implementation Plan

Spec: `docs/specs/2026-07-08-pa-nexus-integration.md` · Date: 2026-07-08
Purpose: the cross-task **contract** for Grok junior implementers. Signatures and build order
only — implementers regenerate exact code/commands from this. One Grok handoff per task; the
senior dev reviews, validates, and commits each.

## File map (new / changed)

```
Nexus/                                  (submodule)
  app/intelligence/sentence_window.py   CHG  add scope filter (task N1)
  app/db/models Document                CHG  add scope column (task N1)
src/perpetual_analyst/
  substrate.py                          NEW  sole Postgres/Nexus boundary (A2, C1, D2, E1)
  config.py                             CHG  Qwen provider defaults, DashScope key (A1)
  analyst/schemas.py                    CHG  NarrativeUpdate bundle; retire TopicAnalysis (D1)
  analyst/synthesis.py                  NEW  daily narrative-update loop (D3)
  analyst/triage.py                     CHG  point triage at Qwen flash (A1)
  daily_run.py                          CHG  ingest→corpus + call synthesis (C2, D4)
  store/topic_map.py                    NEW  SQLite↔Postgres topic id mapping (B2)
  report/render.py                      CHG  render briefing from narrative version (D4)
  retrieval/*                           DEL  FTS5/Voyage retrieval retired (F1)
Nexus/app/db/migrations/versions/       NEW  analytical tables migration (B1)
pyproject.toml                          CHG  add Nexus editable dep; drop voyage/sqlite-vec (A1,F2)
```

## Phase A — Substrate wiring

**A1 — Provider + deps.**
Consumes: `pyproject.toml`, `config.py`, `.env.example`, `analyst/triage.py`.
Produces: Nexus pinned as submodule + editable install; `ModelConfig` defaults `provider="qwen"`,
analyst=`qwen-plus`, judge=`qwen-max`, triage=Qwen flash; `DASHSCOPE_API_KEY`/`LLM_BASE_URL`
loaded and added to the never-log set; Voyage/OpenRouter config removed.

**A2 — `substrate.py` skeleton (ingest + retrieve).**
Consumes: Nexus `ingest_sentence_spans`, `retrieve_windows`, `Embedder`, persist helpers.
Produces:
- `async ingest(topic_id: int, doc: DocInput) -> DocRef` — dedupe by content_hash, persist
  document, sentence-span embed, tag scope=topic_id.
- `async retrieve(topic_id: int, query: str, k: int) -> list[Window]` — topic-scoped hybrid windows.
- `DocInput`, `DocRef`, `Window` dataclasses defined here; no other PA module imports `app.*`.

**N1 — Nexus corpus-scoped retrieval (Nexus repo).**
Consumes: `retrieve_windows`, `_fetch_ann_hits`/`_fetch_lexical_hits`/`_fetch_entity_hits`, `Document`.
Produces: optional `scope` param threaded through retrieval + a scope column on `Document`;
`scope=None` preserves current global behavior (default). Committed to the Nexus submodule.

## Phase B — Analytical schema

**B1 — Alembic migration (Postgres).**
Consumes: Nexus schema (`documents`/`spans`).
Produces: tables `watch_topics`, `source_profiles`, `claims`+`claim_evidence`, `events`,
`narrative_states`, `hypotheses`, `predictions`, `user_preferences`, all with `topic_id` +
indexes per spec §5. Downgrade path included.

**B2 — Topic mapping.**
Consumes: SQLite `topics`, `watch_topics`.
Produces: `store/topic_map.py` — `get_or_create_watch_topic(sqlite_topic) -> topic_id`;
mapping row persisted in SQLite. `watch_topics` mirrors SQLite topics 1:1 by slug.

## Phase C — Daily ingest → corpus

**C1 — Ingest wiring in substrate.** (folded into A2 `ingest`; C1 = the topic-scoped call site.)
Consumes: A2 `ingest`, B2 `topic_map`.
Produces: helper that maps a PA `Item` → `DocInput` and ingests under the topic scope.

**C2 — daily_run ingest stage.**
Consumes: `ingestion/*`, `triage`, C1.
Produces: `daily_run` fetches → content_hash dedupe → Qwen triage filter → `substrate.ingest`
per kept item. No analyst call in this stage.

## Phase D — Narrative-update loop (the daily call)

**D1 — Schemas.**
Consumes: `analyst/schemas.py`.
Produces: `NarrativeUpdate` Pydantic bundle = `{narrative_summary, change_summary,
superseded_claim_ids, claims[], events[], hypotheses[], predictions[], briefing_markdown,
nothing_significant}`; old `TopicAnalysis` marked deprecated (removed in F).

**D2 — substrate synthesis + transactional write.**
Consumes: A2 `retrieve`, D1 schema, Nexus `LLMClient`.
Produces:
- `async synthesize(topic_id, new_doc_refs) -> NarrativeUpdate` — retrieve current narrative +
  top-k claims/windows, one qwen-plus structured call.
- `async persist_bundle(topic_id, bundle) -> WriteResult` — single Postgres transaction: new
  narrative version (`prev_version_id` linked), claim upserts + status flips, hypothesis
  updates (≤7 active, before/after logged), predictions. All-or-nothing (invariant #5).

**D3 — synthesis orchestration.**
Consumes: D2.
Produces: `analyst/synthesis.py::run_daily(topic_id)` → `synthesize` then `persist_bundle`,
returns the bundle for rendering.

**D4 — daily_run analyst stage + render.**
Consumes: D3, `report/render.py`, `delivery/telegram.py`.
Produces: `daily_run` calls `run_daily` per topic (one call/topic/day); dossier rendered as a
projection of the latest narrative version; briefing → Telegram (unchanged). `nothing_significant`
→ one-line entry.

## Phase E — Cross-session query + scoring

**E1 — Ask.**
Consumes: A2, Nexus `answer_sentence_window`.
Produces: `substrate.answer(topic_id, question) -> Answer`; CLI `ask` command wired to it.

**E2 — Prediction scoring + claim decay.**
Consumes: `predictions`, `claims`.
Produces: CLI/cron pass — predictions past `resolve_by` → `hit/miss/expired`; claims past window
→ `stale`. No analyst call.

## Phase F — Cutover

**F1 — Retire old retrieval.** Delete `retrieval/` (FTS5/Voyage) and old `TopicAnalysis`; update callers.
**F2 — Drop dead deps** (`voyageai`, `sqlite-vec`) from `pyproject.toml`; backfill/migrate any
existing PA data into the corpus/analytical tables.

## Build order & parallelism

Sequential spine: A1 → A2 (+N1 in parallel, disjoint repo) → B1 → B2 → C2 → D1 → D2 → D3 → D4 → E → F.
Parallelizable disjoint pairs: {N1 ∥ A2}, {B1 ∥ N1}, {E1 ∥ E2}. Everything in D is sequential
(shared `substrate.py` + schema). F is last (destructive).

## Risks / watch-items

- **Two-DB writes:** bundle atomicity is Postgres-only; SQLite report row after commit,
  idempotent by report_date (spec §10).
- **`substrate.py` is the chokepoint** for D — serialize D tasks to avoid merge churn.
- **Submodule SHA pinning** — PA install must resolve the exact Nexus commit (N1's).
- **No fallback to capsule `/chat/answer`** — retrieval must use the sentence-window path.
- **Grok scope discipline:** N1 commits to the Nexus repo, all else to PA; never `git add -A`.
