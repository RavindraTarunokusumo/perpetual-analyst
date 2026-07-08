from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from perpetual_analyst.analyst.schemas import NarrativeUpdate


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def run_topic_update(
    topic_id: uuid.UUID,
    scope: str,
    focus: str,
    k: int | None = None,
) -> tuple[NarrativeUpdate, dict[str, Any], int]:
    from perpetual_analyst import substrate

    bundle, tokens, ctx = await substrate.synthesize(topic_id, scope, focus, k)
    result = await substrate.persist_bundle(topic_id, bundle, ctx)
    return bundle, result, tokens


def run_topic_update_sync(
    topic_id: uuid.UUID,
    scope: str,
    focus: str,
    k: int | None = None,
) -> tuple[NarrativeUpdate, dict[str, Any], int]:
    return asyncio.run(run_topic_update(topic_id, scope, focus, k))


def run_daily_for_topic(
    slug: str,
    name: str,
    brief: str | None,
    items: Sequence[Any],
    k: int | None = None,
) -> tuple[NarrativeUpdate, dict[str, Any], int]:
    async def _run():
        from perpetual_analyst import substrate

        topic_id = await substrate.get_or_create_watch_topic(slug, name, description=brief)
        ingested = 0
        for it in items:
            if not it.raw_text:
                continue
            published = _parse_iso(it.published_at)
            doc_id = await substrate.ingest(
                slug,
                title=(it.title or ""),
                url=it.url,
                text=it.raw_text,
                published_at=published,
            )
            if doc_id is not None:
                ingested += 1

        item_titles = [it.title or "" for it in items]
        focus = build_focus(brief, item_titles)
        bundle, result, tokens = await run_topic_update(topic_id, slug, focus, k)
        result = {**result, "corpus_ingested": ingested}
        return bundle, result, tokens

    return asyncio.run(_run())


def build_focus(brief: str | None, item_titles: list[str], *, max_titles: int = 12) -> str:
    """Build the retrieval focus query for the day: the topic brief plus the day's
    new item titles (bounded)."""
    parts = []
    if brief:
        parts.append(brief.strip())
    parts.extend(t.strip() for t in item_titles[:max_titles] if t and t.strip())
    return " \n".join(parts) if parts else (brief or "")
