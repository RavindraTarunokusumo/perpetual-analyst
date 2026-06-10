"""Citation rendering: [item:N] → numbered footnote links. See SPEC §6."""

from __future__ import annotations

import re
import sqlite3

_TAG_RE = re.compile(r"\[item:(\d+)\]")


def render_citations(markdown: str, conn: sqlite3.Connection) -> str:
    """Replace [item:N] tags with footnote references.

    - Find all [item:N] tags in markdown
    - For each unique item ID: look up title and url from items table
    - Replace inline [item:N] with [^N] superscript
    - Append a Footnotes section with entries for each cited item
    - Items with no URL: footnote is just "[^N]: {title}" (no link)
    - Items not found in DB: "[^N]: (item N)" as fallback
    """
    ids = [int(m) for m in _TAG_RE.findall(markdown)]
    if not ids:
        return markdown

    unique_ids = sorted(set(ids))

    # Look up each item
    footnotes: dict[int, str] = {}
    for item_id in unique_ids:
        row = conn.execute("SELECT title, url FROM items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            footnotes[item_id] = f"[^{item_id}]: (item {item_id})"
        elif row["url"]:
            title = row["title"] or f"item {item_id}"
            footnotes[item_id] = f"[^{item_id}]: [{title}]({row['url']})"
        else:
            title = row["title"] or f"item {item_id}"
            footnotes[item_id] = f"[^{item_id}]: {title}"

    # Replace inline tags
    result = _TAG_RE.sub(lambda m: f"[^{m.group(1)}]", markdown)

    # Append footnotes section
    footnote_lines = "\n".join(footnotes[i] for i in unique_ids)
    result = result + "\n\n---\n\n" + footnote_lines

    return result
