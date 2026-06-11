# Key Patterns

## Identifier Pattern

- Use integer primary keys internally.
- `topics.slug` is the user-facing identifier (e.g. `ai-frontier-labs`); slugs are stable once created.
- `items` are identified by integer ID; the stable `[item:N]` tag in analyst output uses this ID.
- `content_hash` (SHA-256) is the dedupe key for items, not URL.

## Memory Context Assembly Pattern

The context assembler in `analyst/agent.py` follows this fixed order for prompt caching:

```
[stable — cached across days]
1. system prompt (analyst_system.md)
2. topic brief

[semi-stable — changes weekly]
3. dossier (~1.5K token budget)
4. active theses (≤7, with last update each; stale theses marked `(stale)` by `render_thesis_fragment`)
5. thesis history (`## Thesis history` section via `render_thesis_trail` — confidence trajectory per thesis, e.g. `confidence 0.60→0.80 over N update(s)`)

[daily-volatile — not cached]
6. last 7 days digest lines
6. yesterday's full topic section
7. active observations (importance-sorted, hard-truncated to ~3K tokens)
8. today's triaged items + related prior context

`agent.with_cache_control` attaches an ephemeral `cache_control` breakpoint to the stable system prompt. This helper is applied on both the daily (`run_topic`) and weekly (`run_weekly_review`) model calls so the stable prefix is consistently cached.
```

The context assembler **must** truncate by importance/recency to enforce budgets. It must never exceed `MAX_MEMORY_TOKENS` (set in config or constants). Do not rely on the model to self-limit.

## Transactional Memory Write Pattern

After a successful analyst call, all memory writes must land in one database transaction via `apply_all_memory_writes(topic_id, result, conn)`:

```python
# analyst/memory.py
def apply_all_memory_writes(topic_id: int, result: TopicAnalysis, conn: sqlite3.Connection) -> None:
    with conn:  # sqlite3 context manager — commits on exit, rolls back on exception
        for obs in result.new_observations:
            insert_observation(topic_id, obs, conn)
        for update in result.thesis_updates:
            apply_thesis_update(update, topic_id, conn)
        if result.dossier_edits is not None:
            update_dossier(topic_id, result.dossier_edits, conn)
```

If any write fails, `with conn:` rolls back the entire bundle. Never write observations, thesis updates, or dossier edits outside of this function.

## Weekly Compaction Write Pattern

The weekly run uses two separate write paths with different transactional boundaries:

1. `expire_observations(topic_id, conn)` — pure SQL UPDATE, commits on its own. It is idempotent and safe to re-run.
2. `apply_weekly_review(topic_id, result, conn)` — single `with conn:` bundle: rewrites the dossier, marks promoted observation IDs `status='promoted'`, and appends the self-review note. All three writes commit together or roll back together.

The weekly run never touches `theses` or `thesis_updates`. That write path belongs exclusively to `apply_all_memory_writes` in the daily run, preserving the "theses never silently edited" invariant.

## Structured Output Pattern

Use `client.beta.chat.completions.parse()` (OpenRouter/openai SDK) with a Pydantic model for all analyst calls. Never parse JSON manually from message text. Inject adaptive thinking via `extra_body` when `settings.analyst.thinking` is true.

```python
extra = {"thinking": {"type": "adaptive"}} if settings.analyst.thinking else {}
response = client.beta.chat.completions.parse(
    model=settings.analyst.id,
    messages=messages,
    response_format=TopicAnalysis,
    extra_body=extra,
)
result: TopicAnalysis = response.parsed
```

## Triage-Before-Analyst Pattern

Items are always triaged (Haiku) before the analyst sees them. The analyst never receives raw unscored items. Items with `triage_score < 0.2` are marked `status='skipped'` and never enter the analyst context.

`triage_items` does NOT call `conn.commit()` — it only executes UPDATEs. The caller (e.g. `run_topic`) owns the transaction and commits after all writes are complete. This is consistent with the transactional memory write invariant.

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
        run_topic(topic)
    except Exception as e:
        log.error(f"Topic {topic.slug} failed: {e}")
        continue
```

One failing topic must never stop the run for other topics.

## Citation Pattern

Every item is presented to the analyst with a stable tag `[item:N]` where N is the `items.id`. The analyst must tag claims with these IDs. The renderer converts them to numbered footnote links in the final report. Observations store `source_item_ids` as a JSON array of item IDs.

After report assembly, `_record_citations(report_id, report_date, markdown, conn)` resolves each `[item:N]` tag (via `cited_item_ids` in `render.py`) to its `source_id` and records a row in `citations` (INSERT OR IGNORE — safe to call on re-runs). This citation history feeds `compute_source_quality`.

## Provider-Seam Pattern

The web-search client used for source discovery is isolated behind `web_search_extra()` in `analyst/discovery.py`. Swapping to a different provider (e.g. Perplexity) requires changing only that function and the accompanying `make_client` call — nothing else in the discovery pipeline changes. This seam prevents provider lock-in from spreading into the core discovery logic.

## Source Quality Scoring Pattern

`compute_source_quality(conn)` in `quality.py` runs as a pure-SQL pass after the weekly compaction loop. It computes two sub-scores per source (triage hit-rate and citation rate) and combines them: `quality_score = 0.5*hit_rate + 0.5*citation_rate`. `bottom_decile(conn)` returns the worst-scoring non-probation sources for operator inspection — it does **not** remove them. Sources in probation are excluded from quality ranking until `transition_probation` promotes them. No automated removal ever occurs.

## Code Style

- Comments only when the WHY is non-obvious.
- Prefer clear names over clever abstractions.
- No compatibility shims unless explicitly required.
- Delete dead code.
- No multi-paragraph docstrings.

## Anti-Patterns (from SPEC §15)

**Never do these:**

1. **Multi-agent theater.** No researcher agent, critic agent, debate crews. One model call per topic per day. The only legitimate second call is the Haiku triage function.

2. **Memory science projects.** No knowledge graphs, entity resolution, episodic/semantic taxonomies, reflection trees. Three tables with budgets and an expiry rule deliver 90% of the value.

3. **RAG maximalism.** No vector DB service, no rerankers, no hybrid fusion, no GraphRAG. FTS5 first. Add sqlite-vec only when a concrete retrieval failure is observed.

4. **Ingestion sprawl.** Every new source type is a parser to maintain forever. Add fetchers only for sources proven to be read.

5. **Report inflation.** Every item should not be "significant." Guard `nothing_significant` and the ≤3,000-char digest limit. A report ignored by week three has failed.

6. **Cost drift.** One Opus call per topic per day + Haiku triage is the budget. Revision loops and self-critique passes compound fast. Use prompt caching (stable prefix first).

7. **Infrastructure over judgment.** Every hour on fetchers is an hour not spent in `analyst/prompts/` and `memory.py`. The product lives in the analyst module.
