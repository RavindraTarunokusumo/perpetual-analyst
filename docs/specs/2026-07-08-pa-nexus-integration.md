# PA ↔ Nexus Integration — Design Spec

Status: **accepted (pending user review)** · Date: 2026-07-08 · Owner: solo developer
Supersedes for the affected areas: the standalone retrieval/memory model in `SPEC.md`.
Related: `Nexus/SPEC.md` (Perpetual Analyst on Nexus substrate), `Nexus/docs/architecture.md`
(sentence-window path), root `SPEC.md` (current PA product).

## 1. Goal

Integrate the benchmark-validated **Nexus** memory substrate (sentence-window retrieval,
LongMemEval-500 **0.864** / LoCoMo-48 **0.750**, all-Qwen) into the existing **Perpetual
Analyst** (PA) app without rewriting PA's product. PA keeps its CLI + daily-run + Telegram
shape; Nexus becomes the memory engine PA ingests into and queries. The merge also adopts
Nexus/SPEC.md's analytical memory objects (versioned narrative, claims/events, competing
hypotheses, scored predictions), reconciling them with PA's dossier/theses/observations.

## 2. Decisions (locked with user, 2026-07-08)

1. **Architecture — Nexus as memory substrate.** PA keeps SQLite for operational tables and
   its product surface; Nexus (Postgres/pgvector + sentence-window + Qwen) is the memory
   corpus. PA imports/calls Nexus directly.
2. **Provider — adopt the Qwen stack** (qwen-plus/max + local Qwen3-Embedding-0.6B),
   including the daily analyst and triage calls. Voyage/OpenRouter retired.
3. **Memory model — adopt Nexus/SPEC.md analytical objects** and let them supersede PA's
   legacy objects (§5).
4. **DB topology — two datastores.** SQLite = PA operational/delivery. Postgres = all memory
   (corpus + analytical tables), as Alembic migrations on the Nexus schema.
5. **Daily ingest is one LLM call** (the synthesis call) per topic per day; span embedding
   uses local Qwen3-Embedding and is not counted as the analyst call. Per-source extraction
   (Nexus/SPEC.md §4.1) is **folded into** the single daily synthesis call.
6. **narrative_states is the source of truth**; the dossier becomes a rendered projection;
   PA theses → hypotheses. Old PA objects are superseded, not kept in parallel.

## 3. Architecture

```
PA (this repo)                                  Nexus (submodule, Qwen/Postgres)
├─ ingestion (rss, inbox)  ── content_hash ──┐
├─ triage (Qwen flash fn)                     │  substrate.py
├─ daily_run / weekly_run                     └─▶ ingest_sentence_spans (zero-LLM, topic-scoped)
├─ delivery/telegram        ◀── briefing ─────┐   retrieve_windows (topic-scoped)  ← NEW filter
├─ report/render                              │   answer_sentence_window
└─ store/db (SQLite: ops)                     └── LLMClient (qwen-plus/max), Embedder (Qwen3)
                                                  Postgres: documents/spans + analytical tables
```

- **Dependency:** Nexus is pinned as a **git submodule** at `Nexus/` and installed editable
  (`pip install -e ./Nexus`) into PA's venv. PA imports `app.intelligence.sentence_window`,
  `app.intelligence.embedder.Embedder`, `app.intelligence.llm_client.LLMClient`, and the
  ingestion persist helpers.
- **`perpetual_analyst/substrate.py`** is the single boundary module that touches Postgres /
  Nexus. Public async interface:
  - `ingest(topic_id, document) -> DocumentRef` — persist + dedupe + sentence-span embed,
    tagged with the topic scope.
  - `retrieve(topic_id, query, k) -> list[Window]` — topic-scoped hybrid windows.
  - `answer(topic_id, question) -> Answer` — cross-session grounded Q&A (§6.3).
  - `synthesize(topic_id, new_doc_refs) -> NarrativeUpdate` — the daily loop call (§6.2).
  No other PA module imports `app.*` or connects to Postgres.

## 4. Provider / config

- PA `ModelConfig` default `provider` → `qwen` (DashScope-intl base URL, OpenAI-compatible via
  the existing `openai` client). `analyst` → `qwen-plus`; `judge/synthesis` → `qwen-max`;
  `triage` → a Qwen flash model, still a plain function (not an agent).
- Embeddings → local **Qwen3-Embedding-0.6B @384-dim** via Nexus `Embedder`. `voyageai` and
  `sqlite-vec` dependencies retired.
- Secrets: add `DASHSCOPE_API_KEY` / `LLM_BASE_URL` to config + `.env.example`; add to the
  never-log invariant list. Remove Voyage/OpenRouter keys once retrieval is cut over.

## 5. Data model reconciliation

Analytical tables live in **Postgres**, scoped by `topic_id`, per Nexus/SPEC.md §3
(`watch_topics`, `source_profiles`, `claims` + `claim_evidence`, `events`, `narrative_states`,
`hypotheses`, `predictions`, `user_preferences`). PA operational tables stay in SQLite.

| PA legacy (SQLite) | Merged target | Reconciliation |
|---|---|---|
| `Topic` | `watch_topics` (Postgres) mirrors PA topic 1:1 by slug | PA topic id ↔ `topic_id` mapping stored in SQLite `topics` |
| `Dossier` (mutable text) | latest `narrative_states` row | dossier is a **rendered projection** of the current narrative version; not independently edited |
| `Thesis` / `ThesisUpdate` | `hypotheses` + confidence-change log | competing hypotheses; keep "never silently edited / log before-after / ≤7 active per topic" |
| `Observation` | `claims` + `events` | source-backed, span-linked; materialized inside the daily call |
| `Source` | `source_profiles` (+ PA `sources` for fetch/quality state) | reliability/incentive move to Postgres; fetch lifecycle stays SQLite |
| `Item` | SQLite `items` + Nexus `documents`/`spans` | item text ingested into the corpus; `content_hash` dedupe preserved |
| — | `predictions` | new; scored `open→hit/miss/expired` |

`entities_json` holds string lists (no entity resolution in MVP; string-match coref only).

**Reconciliation with Nexus's existing schema (discovered during B1):** Nexus already ships
`claims` + `claim_evidence` tables (from its 0001 schema, shaped for the now-scrapped capsule
ontology: `claim_type NOT NULL`, no `topic_id`/`source_authority`, no embedding). PA **reuses**
these rather than duplicating: B1 extends `claims` with nullable `topic_id` (FK `watch_topics`)
and `source_authority`, and relaxes `claim_type` to nullable. `claim_evidence(claim_id, span_id,
evidence_role, quote)` already matches PA's evidence need and is reused as-is. Nexus's scrapped
`theses`/`decision_artefacts`/`semantic_*` tables are left untouched (empty; ignored by PA).

**Claim/event embeddings are deferred** (MVP deviation from Nexus/SPEC.md §3). A topic's active
claim/event set is small and is retrieved wholesale by `topic_id` + status/recency for the daily
call; per-claim ANN (a pgvector column on `claims`/`events`) is added only if that set outgrows
the retrieved subset. Corpus retrieval (spans) still carries embeddings — only claim/event-level
ANN is deferred.

## 6. Workflows

### 6.1 Daily ingest → corpus (zero LLM except triage)
1. RSS/inbox fetch → `content_hash` dedupe (silent skip on dup, invariant #8).
2. **Qwen triage function** scores/filters items (one cheap call, a function not an agent).
3. Kept items → `substrate.ingest(topic_id, doc)` → Nexus deterministic sentence-span ingest,
   embedded with Qwen3, tagged with topic scope. No extraction call here.

### 6.2 Daily analyst call = narrative-update loop (one qwen-plus call / topic / day)
1. Retrieve topic-scoped windows for today's new material + the current `narrative_states`
   version + relevant prior claims (top-k bounded; never O(n²) over the corpus).
2. **One structured synthesis call** emits a `NarrativeUpdate` bundle: new/updated
   `claims`+`events` (from retrieved spans), a **new narrative version** with `change_summary`
   and `prev_version_id`, hypothesis updates (supporting/contradicting sets, confidence,
   spawn/retire vs `invalidation_criteria`), `predictions`, and the briefing markdown.
3. **Transactional write** of the whole bundle — all objects persist together or none
   (invariant #5). Claim `status` flips happen in the same transaction.
4. Render briefing from the new narrative version → **Telegram** digest + full report
   (unchanged delivery). `nothing_significant: true` stays a first-class one-line output.

### 6.2b Persist-bundle mapping (D2b decisions)
The transactional write of a `NarrativeUpdate` (invariant #5) resolves the bundle's index-space
references using the synthesis **context** (the retrieved windows + the ordered prior-claim list
`synthesize` used), returned alongside the bundle. Mapping:
- **claims** → new `claims` rows (`claim_type` NULL, `document_id` NULL — migration 0010 makes it
  nullable; a synthesized claim isn't owned by one document). `evidence_span_indices` index the
  retrieved windows; each resolves to that window's `span_ids` → `claim_evidence` rows (real
  provenance for the inspector).
- **superseded_claim_ids** index the prior active-claim list → flip those claims to `superseded`.
- **events** → `events`; `claim_refs` index the bundle's new claims → stored as `claim_ids`.
- **narrative** → a new `narrative_states` version (`version=prev+1`, `prev_version_id` linked);
  `supporting_claim_ids` = the new claim ids.
- **hypotheses (deviation from invariant #3):** the bundle's hypotheses are treated as the new
  active set — prior active hypotheses are **retired** and the new ones inserted (capped ≤7),
  rather than edited in place with an explicit before/after confidence log. History is preserved
  as `retired` rows; the confidence trajectory is visible across rows but there is no per-edit
  delta record. Simpler and snapshot-consistent for the MVP; revisit if per-hypothesis audit is needed.
- **predictions** → open `predictions`; `resolve_by = today + horizon_days`; `hypothesis_id` NULL
  (the schema carries no hypothesis ref in the MVP).
- **source_profiles** → `source_profiles`.
If `nothing_significant`, persist writes nothing (no new narrative version).

### 6.3 Cross-session query & lifecycle
- Ask ("current view" / "competing hypotheses" / "did your prediction resolve") answered from
  persistent objects via `substrate.answer` (Nexus Chain-of-Note reader), topic-scoped.
- `predictions resolve` + claim-decay (`active→stale`) run as a separate CLI/cron pass — no
  extra daily analyst call.

## 7. Upstream change (Nexus repo)

**Corpus/topic-scoped retrieval** — the one required change inside the Nexus submodule
(already tracked as an open item in `Nexus/TODO.md`): thread a `scope` (topic/corpus id) filter
through `retrieve_windows` and `_fetch_ann_hits` / `_fetch_lexical_hits` / `_fetch_entity_hits`,
backed by a scope column on `Document`. Committed to the Nexus repo. The unscoped path stays
the default so existing Nexus behavior is unchanged; no benchmark re-run required. All other
work lands in PA.

## 8. Invariant / spec changes to record

- Provider Anthropic/OpenRouter → **Qwen**; add DashScope key to the never-log list (inv #7).
- Inv #1 reaffirmed: still one analyst call per topic per day; extraction folded in; triage is
  a Qwen function.
- Inv #3 reframed onto `hypotheses` (never silently edited; before/after logged; ≤7 active).
- Inv #8 `content_hash` dedupe preserved via Nexus URL/content dedupe.
- **Telegram retained** — deliberate, documented deviation from Nexus/SPEC.md §9.
- `SPEC.md` and `CLAUDE.md`/`AGENTS.md` Core Invariants updated to match (same edit to both).

## 9. Phased build order (→ implementation plan)

- **A — Substrate wiring:** Nexus submodule + editable install; Qwen provider config; Postgres
  up; `substrate.py` (ingest/retrieve); **Nexus corpus-scoped retrieval** change (unscoped
  path stays default; no benchmark re-run).
- **B — Analytical schema:** Alembic migrations for the 8 analytical tables on Postgres; PA↔Nexus
  topic mapping.
- **C — Daily ingest → corpus:** route RSS/inbox through `substrate.ingest`; keep Qwen triage.
- **D — Narrative-update loop:** `NarrativeUpdate` schema + prompt; the single daily call;
  transactional bundle write; dossier-as-projection; theses→hypotheses.
- **E — Cross-session query + prediction scoring** pass; Telegram reads the rendered briefing.
- **F — Cutover:** retire FTS5/Voyage retrieval + old `TopicAnalysis` schema; backfill/migrate;
  drop dead deps.

Each phase is delegated to Grok junior implementers per the 7-step workflow; phase A and the
Nexus-repo change are committed to their respective repos (PA vs Nexus submodule).

## 10. Edge cases / risks

- **Two-DB transactionality:** the daily bundle write is atomic *within Postgres*; SItes SQLite
  the SQLite report/delivery rows are written after the Postgres commit and are idempotent by report_date.
- **Cross-repo drift:** Nexus is pinned by submodule SHA; PA CI installs that exact SHA.
- **Benchmark transfer:** quality numbers hold only on the Qwen stack + sentence-window path;
  cutover (F) must not silently fall back to the capsule `/chat/answer` route.
- **Narrative thrash:** require ≥N corroborating claims / a confidence threshold before a
  narrative version flips (tune on the demo corpus).
- **Prediction without ground truth** → `expired`, never fabricated.
- **Postgres now required to run PA** — the zero-ops SQLite-only story ends; documented in ops.
- **Global `content_hash` dedupe is cross-topic** (invariant #8): a document has one `scope`, so
  the same article ingested under two topics is stored once under whichever ingested first; the
  second topic's scoped retrieval won't see it. Acceptable for the single-domain MVP; if
  multi-topic source overlap matters later, move dedupe to per-(scope,content_hash).
- **Substrate engine is event-loop-bound** (asyncpg): `daily_run` calls `asyncio.run()` per topic,
  so `substrate._session_factory()` caches the engine per running loop and rebuilds on loop change.

## 11. Open decisions (defer to plan)

- Exact top-k / corroboration threshold for narrative flips.
- Whether `watch_topics` is authoritative or a mirror of SQLite `topics` (leaning mirror).
- Prediction scoring cadence (nightly CLI vs on-ingest).
- Submodule vs vendored copy if submodule tooling proves awkward in CI.

## 12. Success criteria

1. PA's daily run ingests into the Nexus corpus and produces a briefing from **one** qwen-plus
   call per topic per day.
2. Memory objects (claims/events/narrative/hypotheses/predictions) persist in Postgres, scoped
   by topic, and are browsable.
3. The narrative-update loop produces a **versioned** diff (before/after + reason).
4. Retrieval is topic-scoped (no global leakage) and uses the sentence-window path.
5. Telegram delivery still works end to end.
6. The corpus-scoped retrieval change leaves the unscoped Nexus path behaving as before.
