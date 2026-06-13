"""Citation rendering: [item:N] -> numbered footnote links. See SPEC §6/§9."""

from __future__ import annotations

import re
import sqlite3

_ITEM_TAG_RE = re.compile(r"\[item:(\d+)\]")


def render_citations(markdown: str, conn: sqlite3.Connection) -> str:
    """Replace [item:N] with [^k] footnotes; unknown ids render as plain text.

    [obs:N]/[thesis:N] tags are internal memory references and pass through.
    """
    numbering: dict[int, int] = {}
    rows: dict[int, sqlite3.Row] = {}

    def _replace(match: re.Match[str]) -> str:
        item_id = int(match.group(1))
        if item_id not in rows:
            row = conn.execute("SELECT title, url FROM items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                return f"item:{item_id}"
            rows[item_id] = row
            numbering[item_id] = len(numbering) + 1
        return f"[^{numbering[item_id]}]"

    body = _ITEM_TAG_RE.sub(_replace, markdown)
    if not numbering:
        return body

    lines = ["", "## Sources reviewed", ""]
    for item_id, k in sorted(numbering.items(), key=lambda pair: pair[1]):
        row = rows[item_id]
        title = row["title"] or "(untitled)"
        url = row["url"] or "(no url)"
        lines.append(f"[^{k}]: {title} — {url}")
    return body + "\n".join(lines) + "\n"
