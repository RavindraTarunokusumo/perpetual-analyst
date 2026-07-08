from __future__ import annotations

import asyncio
import uuid
from typing import Any

from perpetual_analyst.analyst.schemas import NarrativeUpdate


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


def build_focus(brief: str | None, item_titles: list[str], *, max_titles: int = 12) -> str:
    """Build the retrieval focus query for the day: the topic brief plus the day's
    new item titles (bounded)."""
    parts = []
    if brief:
        parts.append(brief.strip())
    parts.extend(t.strip() for t in item_titles[:max_titles] if t and t.strip())
    return " \n".join(parts) if parts else (brief or "")
