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

## Clamping Validator Pattern

Provider structured-output schemas reject Pydantic `ge`/`le` field constraints because these emit `minimum`/`maximum` in JSON Schema, which OpenRouter's structured output endpoint refuses. Use `@field_validator` with clamping instead:

```python
@field_validator("confidence", mode="before")
@classmethod
def clamp_confidence(cls, v: float) -> float:
    return max(0.0, min(1.0, float(v)))
```

Apply this to any numeric field sent through `client.beta.chat.completions.parse()`.

## Config Sync Pattern

YAML files (`config/topics.yaml`, `config/sources.yaml`) are the source of truth for topic/source definitions. `sync_config(conn, topics, sources)` performs an idempotent upsert: rows present in YAML are created-or-updated; rows absent from YAML are deactivated. Runtime-only columns (`last_fetched_at`, `fetch_error_count`) are never touched by `sync_config`. `inbox`-type sources are exempt from YAML-absence deactivation.

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
result: TopicAnalysis = response.choices[0].message.parsed  # real SDK shape
```

## Triage-Before-Analyst Pattern

Items are always triaged (Haiku) before the analyst sees them. The analyst never receives raw unscored items. Items with `triage_score < 0.2` are marked `status='skipped'` and never enter the analyst context.

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

## Code Style

- Comments only when the WHY is non-obvious.
- Prefer clear names over clever abstractions.
- No compatibility shims unless explicitly required.
- Delete dead code.
- No multi-paragraph docstrings.

## Env-Gated External Delivery Pattern

External delivery (`delivery/telegram.py`) is gated on the presence of `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` at call time. The function never raises — on failure it prints the exception *type* only (no token/chat-id values) and returns. Undelivered reports are retried on the next run via `retry_undelivered(conn)`, which sweeps `reports` rows where `delivered_at IS NULL`. This decouples delivery failures from the analysis pipeline: a Telegram outage never prevents the report from being stored or the next day's analysis from proceeding.

## Empty-Items Short-Circuit Pattern

`run_topic` checks for an empty item list before making any LLM call. When no items pass triage (`nothing_significant` short-circuit), it returns a synthetic `TopicAnalysis(nothing_significant=True)` with no API call. This enforces Invariant 1 (one analyst call per topic per day) and avoids wasting API budget on topics with no new signal.

## One Daily Digest Call Pattern

`assemble_report` makes exactly one `DigestOutput` structured call per day on the analyst model after all per-topic sections are assembled. This is the only sanctioned extension to Invariant 1. The call uses a mechanical fallback (concatenated section text) if the model call fails, so a digest failure never blocks report persistence or delivery.

## Web Layer Write Pattern

All web write actions must route through existing guarded paths — never issue bare SQL from routes or `actions.py`. The three sanctioned writes are:

- `add_inbox_item` → `store.db.insert_item` (enforces content-hash dedupe)
- `retry_all` → `delivery.telegram.retry_undelivered` (env-gated)
- `trigger_run` → `daily_run.run_daily` (threading.Lock — single active run)

Action error handlers expose `type(exc).__name__` only; never the exception message (Invariant 7 — no secret leakage through the UI).

## CSRF Guard Pattern (Loopback Tool)

For a no-auth loopback-only tool, reject cross-origin state-changing requests in `before_request`:

```python
@app.before_request
def _csrf_origin_guard() -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("Origin")
    if origin is not None and urlparse(origin).netloc != request.host:
        abort(403)
```

Browsers always send `Origin` on cross-origin POSTs; same-origin form submits and non-browser clients (no `Origin` header) pass through. This is sufficient for a single-user loopback tool — it is not a substitute for session auth on a networked service.

## Anti-Patterns (from SPEC §15)

**Never do these:**

1. **Multi-agent theater.** No researcher agent, critic agent, debate crews. One model call per topic per day. The only legitimate second call is the Haiku triage function.

2. **Memory science projects.** No knowledge graphs, entity resolution, episodic/semantic taxonomies, reflection trees. Three tables with budgets and an expiry rule deliver 90% of the value.

3. **RAG maximalism.** No vector DB service, no rerankers, no hybrid fusion, no GraphRAG. FTS5 first. Add sqlite-vec only when a concrete retrieval failure is observed.

4. **Ingestion sprawl.** Every new source type is a parser to maintain forever. Add fetchers only for sources proven to be read.

5. **Report inflation.** Every item should not be "significant." Guard `nothing_significant` and the ≤3,000-char digest limit. A report ignored by week three has failed.

6. **Cost drift.** One Opus call per topic per day + Haiku triage is the budget. Revision loops and self-critique passes compound fast. Use prompt caching (stable prefix first).

7. **Infrastructure over judgment.** Every hour on fetchers is an hour not spent in `analyst/prompts/` and `memory.py`. The product lives in the analyst module.
