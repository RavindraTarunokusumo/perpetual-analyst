"""FTS5 keyword search helpers for the analyst's related-context retrieval. See SPEC §6."""

# TODO (Task 8): Implement
# - related_observations(text: str, topic_id: int, db: Connection, k: int = 5) -> list[Observation]
#   - FTS5 query against observations_fts
#   - join with observations WHERE topic_id = ? AND status = 'active'
#   - recency weight: boost observations from last 30 days
#
# - related_items(text: str, topic_id: int, db: Connection, k: int = 3) -> list[Item]
#   - FTS5 query against items_fts
#   - join with items via topic_sources
#   - recency weight: boost items from last 14 days
#
# V1: keyword search only. No vectors, no embeddings.
# Phase 2+: add embeddings.py with sqlite-vec only when FTS proves insufficient.
