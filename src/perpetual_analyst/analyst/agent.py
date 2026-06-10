"""Context assembly + LLM call + memory persistence for one topic per day. See SPEC §7."""

# TODO (Task 4): Implement
# - assemble_context(topic_id, items, db) -> list[dict]  # caching-friendly order
# - run_topic(topic_id, db, dry_run=False) -> TopicAnalysis
#   - calls client.messages.parse() with claude-opus-4-8, adaptive thinking
#   - persists all returned memory writes transactionally
#   - dry_run=True: print assembled prompt, return None
#
# Context assembly order (MUST follow this for prompt caching):
#   1. system prompt (analyst_system.md) — stable, cached
#   2. topic brief — stable, cached
#   3. dossier — semi-stable
#   4. active theses + last update each — semi-stable
#   5. last 7 days digest lines — daily-volatile
#   6. yesterday's full topic section — daily-volatile
#   7. active observations (importance-sorted, budget-truncated) — daily-volatile
#   8. today's triaged items + related prior context — daily-volatile
