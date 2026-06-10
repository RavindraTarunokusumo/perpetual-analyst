"""RSS/Atom feed fetcher using feedparser + trafilatura. See SPEC §12 Phase 2."""

# TODO (Task 7): Implement
# - fetch_rss(source: Source, db: Connection) -> list[Item]
#   - parse feed with feedparser
#   - filter entries newer than source.last_fetched_at
#   - extract full article text with trafilatura (graceful fallback to feed summary)
#   - hash-dedupe on content_hash
#   - INSERT OR IGNORE into items
#   - update sources.last_fetched_at on success
#   - increment sources.fetch_error_count on failure (max 5 before marking inactive)
