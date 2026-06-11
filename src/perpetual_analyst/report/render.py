"""Citation rendering: [item:N] → numbered footnote links. See SPEC §6."""

from __future__ import annotations

import re
import sqlite3

_TAG_RE = re.compile(r"\[item:(\d+)\]")


def cited_item_ids(markdown: str) -> list[int]:
    """Return unique [item:N] ids in document order from analyst markdown."""
    seen: dict[int, None] = {}
    for m in _TAG_RE.findall(markdown):
        seen.setdefault(int(m), None)
    return list(seen)


def render_citations(markdown: str, conn: sqlite3.Connection) -> str:
    """Replace [item:N] tags with footnote references.

    - Find all [item:N] tags in markdown
    - For each unique item ID: look up title and url from items table
    - Replace inline [item:N] with [^N] superscript
    - Append a Footnotes section with entries for each cited item
    - Items with no URL: footnote is just "[^N]: {title}" (no link)
    - Items not found in DB: "[^N]: (item N)" as fallback
    """
    if not cited_item_ids(markdown):
        return markdown

    unique_ids = sorted(set(cited_item_ids(markdown)))

    # Batch-fetch all cited items in one query
    placeholders = ",".join("?" * len(unique_ids))
    rows = conn.execute(
        f"SELECT id, title, url FROM items WHERE id IN ({placeholders})", unique_ids
    ).fetchall()
    found = {row["id"]: row for row in rows}

    footnotes: dict[int, str] = {}
    for item_id in unique_ids:
        row = found.get(item_id)
        if row is None:
            footnotes[item_id] = f"[^{item_id}]: (item {item_id})"
        else:
            title = row["title"] or f"item {item_id}"
            footnotes[item_id] = (
                f"[^{item_id}]: [{title}]({row['url']})" if row["url"] else f"[^{item_id}]: {title}"
            )

    # Replace inline tags
    result = _TAG_RE.sub(lambda m: f"[^{m.group(1)}]", markdown)

    # Append footnotes section
    footnote_lines = "\n".join(footnotes[i] for i in unique_ids)
    result = result + "\n\n---\n\n" + footnote_lines

    return result
