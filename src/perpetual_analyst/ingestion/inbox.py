"""Scan inbox/<topic-slug>/ for .md/.txt/.pdf, extract text, hash-dedupe, write items."""

# TODO (Task 5): Implement
# - scan_inbox(topic_slug: str, db: Connection) -> list[Item]
#   - walk inbox/<topic-slug>/
#   - extract text: pypdf for .pdf, plain read for .md/.txt
#   - compute content_hash = sha256(raw_text.strip())
#   - INSERT OR IGNORE INTO items (content_hash dedupes)
#   - move processed files to inbox/<slug>/.processed/ to avoid re-ingestion
#   - return list of newly inserted Item rows
