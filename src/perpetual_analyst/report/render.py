"""Citation rendering: [item:N] → numbered footnote links. See SPEC §6."""

# TODO (Task 9): Implement
# - render_citations(markdown: str, db: Connection) -> str
#   - find all [item:N] tags in markdown
#   - look up item title and URL from DB
#   - replace inline tags with [^N] superscripts
#   - append footnotes section: [^N]: [title](url)
