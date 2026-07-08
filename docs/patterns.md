# Key Patterns

## Identifier Pattern

- Use integer primary keys internally in SQLite; UUID primary keys in Postgres analytical tables.
- `topics.slug` is the user-facing identifier (e.g. `ai-frontier-labs`); slugs are stable once created and map to `watch_topics.slug` in Postgres.
- `items` are identified by integer ID in SQLite; corpus provenance links through Postgres `claim_evidence` → `spans`.
- `content_hash` (SHA-256) is the dedupe key for items/documents, not URL.

## Synthesis Context Assembly Pattern

The daily analyst call assembles context in `substrate.synthesize` before the single structured
synthesis call. Retrieval is structural — bounded by sentence-window `top_k`, not by prompting
the model to self-limit.

```
[retrieved — topic-scoped sentence windows from pgvector]
→ current narrative_states version (source of truth)
→ active claims (status=active, recency-bounded)
→ active hypotheses (≤7)
→ open predictions
→ today's new source passages
→ JSON schema for NarrativeUpdate
```

Focus query for retrieval is built in `synthesis.build_focus`: topic brief + today's item titles (bounded). Do not rely on the model to self-limit context size.

## Transactional Memory Write Pattern

After a successful synthesis call, all analytical writes must land in one Postgres transaction via
`substrate.persist_bundle(topic_id, bundle, ctx)`:

```python
# substrate.py — simplified
async def persist_bundle(topic_id, bundle: NarrativeUpdate, ctx: SynthesisContext):
    if bundle.nothing_significant:
        return {"skipped": True, ...}
    async with factory() as session:
        # claims + claim_evidence, events, narrative_states version,
        # hypotheses (retire prior active, insert new ≤7), predictions, source_profiles
        await session.commit()
```

If any write fails, the session rolls back the entire bundle. Never write claims, narrative versions, or hypotheses outside of `persist_bundle`.

When `nothing_significant` is true, `persist_bundle` writes nothing (no new narrative version).

## Weekly Compaction Write Pattern

The weekly run uses two separate write paths with different transactional boundaries (SQLite legacy path):

1. `expire_observations(topic_id, conn)` — pure SQL UPDATE, commits on its own. It is idempotent and safe to re-run.
2. `apply_weekly_review(topic_id, result, conn)` — single `with conn:` bundle: rewrites the dossier, marks promoted observation IDs `status='promoted'`, and appends the self-review note. All three writes commit together or roll back together.

The weekly run operates on SQLite dossiers/observations/theses. Daily hypotheses live in Postgres and are managed exclusively by `persist_bundle`.

## Structured Output Pattern

The daily analyst call uses Nexus `LLMClient.complete_json()` with the `NarrativeUpdate` Pydantic model. Never parse JSON manually from message text.

```python
result, tokens = await client.complete_json(
    model=settings.t3_model,  # qwen3.7-max
    system=_SYNTHESIS_SYSTEM,
    user=user_prompt,
    response_model=NarrativeUpdate,
    run_type="narrative_update",
)
```

Digest generation in `report/assemble.py` uses the OpenAI-compatible client with `settings.analyst.id` (`qwen3.7-plus`).

## Triage-Before-Synthesis Pattern

Items are always triaged (Qwen flash) before corpus ingest and synthesis. The analyst never receives raw unscored items. Items with `triage_score < 0.2` are marked `status='skipped'` and never enter the synthesis path.

`triage_items` does NOT call `conn.commit()` — it only executes UPDATEs. The caller owns the transaction and commits after all writes are complete.

## Datetime Filter Pattern

In `fetch_rss`, the since-last-fetch filter compares entry publish time against `source.last_fetched_at` by parsing both as UTC-naive `datetime` objects via `_parse_as_utc_naive()`. String comparison is not used because feed datetime strings can have different formats and timezone suffixes.

```python
pub_dt = _parse_as_utc_naive(published_iso)
last_dt = _parse_as_utc_naive(source.last_fetched_at)
if pub_dt is not None and last_dt is not None and pub_dt <= last_dt:
    continue
```

## Shared Inbox Source Helper Pattern

`get_or_create_inbox_source(conn, topic_id, topic_slug) -> int` in `ingestion/inbox.py` is the canonical path for creating or looking up the inbox source for a topic. Both `cli.py` and `daily_run.py` call this function — never duplicate the INSERT/SELECT inline.

## Deduplication Pattern

Item ingestion must always go through `store.db.insert_item(conn, source_id, content_hash, ...)`. This is the only safe insertion path — it executes `INSERT OR IGNORE` and returns `True` if inserted, `False` if the `content_hash` already exists. Never write a bare `INSERT INTO items` in ingestion code.

Corpus ingest uses the same invariant via Nexus `_persist_document` + `content_hash`; duplicates return `None` from `substrate.ingest`.

```python
from perpetual_analyst.store.db import insert_item

inserted = insert_item(conn, source_id=src.id, content_hash=sha256_hex, title=title, raw_text=text)
# inserted is False → duplicate, silently skip
```

The fetcher computes `content_hash = sha256(raw_text.strip().encode()).hexdigest()` before calling `insert_item`. Duplicate content from different URLs is silently ignored.

## Error Isolation Pattern

In `daily_run.py`, each topic's analysis runs in its own try/except:

```python
for topic in active_topics:
    try:
        # ingest → triage → corpus → synthesis
        ...
    except Exception as e:
        log.error(f"Topic {topic.slug} failed: {e}")
        continue
```

One failing topic must never stop the run for other topics.

## Provenance Pattern

Daily reports are assembled from `NarrativeUpdate.briefing_markdown` — no `[item:N]` citation rendering. Source provenance lives in Postgres `claim_evidence` rows linking claims to `spans`. Cross-session Q&A (`analyst ask`) returns grounded answers with citation labels from the Nexus reader.

Historical `citations` SQLite rows (from the pre-Nexus report path) may still feed `compute_source_quality` for older reports.

## Source Approval Pattern

Discovered sources are never auto-added. `discover_sources()` writes
`source_candidates` rows with `status='pending'`; operator approval happens in
`analyst/candidates.py` through the local Web UI.

Approval must validate the candidate URL before any fetch:

- only HTTP(S)
- hostname required
- no URL credentials
- no localhost, private, loopback, link-local, multicast, reserved, or
  unspecified addresses
- DNS resolution must not point at private/reserved addresses
- every redirect target is validated before following

Approved candidates create probation sources and topic links. Rejected
candidates stay as rejected rows. No source is removed automatically.

## Provider-Seam Pattern

Daily calls (triage, synthesis, digest) use the Qwen stack via DashScope-intl
(`make_client("qwen")`, secrets in `Nexus/.env`). Weekly source discovery may use
`openrouter_web` or `perplexity` from settings via `make_client(provider=...)` and
`web_search_extra(provider)` without changing the daily Qwen client.

## Source Quality Scoring Pattern

`compute_source_quality(conn)` in `quality.py` runs as a deterministic pass after
the weekly compaction loop. It computes four sub-scores per source: triage
hit-rate, citation rate, uniqueness rate, and freshness-lead rate. The current
schema has no explicit development IDs, so uniqueness and freshness use report
citation groups as the measurable proxy. The score is:

`0.35*hit_rate + 0.35*citation_rate + 0.15*uniqueness_rate + 0.15*freshness_lead_rate`.

`bottom_decile(conn)` returns the worst-scoring non-probation sources for
operator inspection. It does **not** remove anything. Sources in probation are
excluded from quality ranking until `transition_probation` promotes them. No
automated removal ever occurs.

## Corpus Ingest Pattern

Daily corpus ingest is zero-LLM: `substrate.ingest` persists the document, then
`ingest_sentence_spans` sentence-splits and embeds locally (BAAI/bge-small-en-v1.5,
384-dim). Documents are tagged with `scope=topic.slug` for topic-scoped retrieval.
Only `substrate.py` may call Nexus ingestion helpers.

## Code Style

- Comments only when the WHY is non-obvious.
- Prefer clear names over clever abstractions.
- No compatibility shims unless explicitly required.
- Delete dead code.
- No multi-paragraph docstrings.

## Anti-Patterns (from SPEC §15)

**Never do these:**

1. **Multi-agent theater.** No researcher agent, critic agent, debate crews. One synthesis call per topic per day. The only legitimate second call is the Qwen flash triage function.

2. **Memory science projects.** No knowledge graphs, entity resolution, episodic/semantic taxonomies, reflection trees. Versioned narrative + claims + hypotheses with budgets deliver the value.

3. **RAG maximalism.** No separate vector DB service, no rerankers, no GraphRAG. Nexus sentence-window over pgvector spans is the retrieval path. Do not fall back to FTS5 or sqlite-vec on the daily path.

4. **Ingestion sprawl.** Every new source type is a parser to maintain forever. Add fetchers only for sources proven to be read.

5. **Report inflation.** Every item should not be "significant." Guard `nothing_significant` and the ≤3,000-char digest limit. A report ignored by week three has failed.

6. **Cost drift.** One synthesis call per topic per day + Qwen flash triage is the budget. Revision loops and self-critique passes compound fast.

7. **Infrastructure over judgment.** Every hour on fetchers is an hour not spent in synthesis prompts and `substrate.py`. The product lives in the narrative-update loop.