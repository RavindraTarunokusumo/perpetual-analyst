from __future__ import annotations

import hashlib
import re
import shutil
import sqlite3
from pathlib import Path

from perpetual_analyst.store.db import insert_item
from perpetual_analyst.store.models import Item

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


def _extract_text(path: Path) -> str | None:
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def scan_inbox(
    topic_slug: str,
    topic_id: int,
    source_id: int,
    conn: sqlite3.Connection,
) -> list[Item]:
    if not _SLUG_RE.match(topic_slug):
        raise ValueError(f"Invalid topic_slug: {topic_slug!r}")

    inbox_base = Path("inbox").resolve()
    inbox_dir = (inbox_base / topic_slug).resolve()
    if not inbox_dir.is_relative_to(inbox_base):
        raise ValueError(f"topic_slug escapes inbox: {topic_slug!r}")

    processed_dir = inbox_dir / ".processed"

    if not inbox_dir.exists():
        return []

    processed_dir.mkdir(parents=True, exist_ok=True)
    inserted: list[Item] = []

    for path in sorted(inbox_dir.iterdir()):
        if path.name.startswith(".") or path.is_dir():
            continue
        if path.suffix.lower() not in {".pdf", ".md", ".txt"}:
            continue

        raw_text = _extract_text(path)
        if not raw_text or not raw_text.strip():
            continue

        content_hash = hashlib.sha256(raw_text.strip().encode()).hexdigest()

        is_new = insert_item(
            conn,
            source_id=source_id,
            content_hash=content_hash,
            title=path.stem,
            raw_text=raw_text,
        )
        conn.commit()

        dest = processed_dir / path.name
        shutil.move(str(path), str(dest))

        if is_new:
            row = conn.execute(
                "SELECT * FROM items WHERE content_hash = ?", (content_hash,)
            ).fetchone()
            inserted.append(Item.from_row(row))

    return inserted
