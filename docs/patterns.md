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
4. active theses (≤7, with last update each)

[daily-volatile — not cached]
5. last 7 days digest lines
6. yesterday's full topic section
7. active observations (importance-sorted, hard-truncated to ~3K tokens)
8. today's triaged items + related prior context
```

The context assembler **must** truncate by importance/recency to enforce budgets. It must never exceed `MAX_MEMORY_TOKENS` (set in config or constants). Do not rely on the model to self-limit.

## Transactional Memory Write Pattern

After a successful `client.messages.parse()` call, all memory writes must land in one database transaction:

```python
with db.transaction():
    memory.apply_observation_writes(result.new_observations)
    theses.apply_thesis_updates(result.thesis_updates)
    if result.dossier_edits:
        memory.update_dossier(topic_id, result.dossier_edits)
```

If any write fails, the transaction rolls back. The report section is not written to `reports` until all memory writes succeed.

## Structured Output Pattern

Use `client.messages.parse()` with a Pydantic model for all analyst calls. Never parse JSON manually from message text.

```python
response = client.messages.parse(
    model="claude-opus-4-8",
    thinking={"type": "adaptive"},
    output_config={"effort": "high"},
    messages=[...],
    response_format=TopicAnalysis,
)
result: TopicAnalysis = response.parsed
```

## Triage-Before-Analyst Pattern

Items are always triaged (Haiku) before the analyst sees them. The analyst never receives raw unscored items. Items with `triage_score < 0.2` are marked `status='skipped'` and never enter the analyst context.

## Deduplication Pattern

Item ingestion always uses `INSERT OR IGNORE INTO items (...) WHERE content_hash = ?`. The fetcher computes `content_hash = sha256(raw_text.strip())` before inserting. Duplicate content from different URLs is silently ignored.

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
