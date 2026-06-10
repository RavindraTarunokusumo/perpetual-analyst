"""Haiku relevance triage pass — score + 2-line summary per item. See SPEC §4."""

# TODO (Task 7): Implement
# - triage_items(items: list[Item], topic_brief: str, client) -> list[TriagedItem]
#   - batch call to claude-haiku-4-5
#   - returns relevance score (0–1) and 2-line summary per item
#   - items with score < 0.2 are marked status='skipped'
#   - items with score >= 0.2 are marked status='analyzed' after analyst run
#
# The triage pass exists to protect the analyst's context window:
# the expensive Opus model sees 10–30 distilled items, not 200 raw articles.
