"""Haiku relevance triage pass — score + 2-line summary per item. See SPEC §4."""

from __future__ import annotations

import json
import logging
import sqlite3

import openai

from perpetual_analyst.config import Settings
from perpetual_analyst.store.models import Item

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a relevance filter. For each item, output a JSON array of objects "
    "with fields: item_id (int), score (float 0-1), summary (str, max 2 sentences). "
    "Score reflects relevance to the topic brief. "
    "Be strict: score < 0.2 = not relevant."
)


def triage_items(
    items: list[Item],
    topic_brief: str,
    client: openai.OpenAI,
    settings: Settings,
    conn: sqlite3.Connection,
) -> list[Item]:
    """Score items for relevance to the topic brief using the triage model.

    Returns items with triage_score >= 0.2.
    On API failure: logs warning, returns all items unchanged (graceful degradation).
    """
    if not items:
        return []

    items_payload = "\n".join(
        f"item_id={item.id} title={item.title or '(untitled)'} "
        f"text={( item.raw_text or '')[:300]}"
        for item in items
    )
    user_message = f"Topic brief: {topic_brief}\n\nItems:\n{items_payload}"

    try:
        response = client.chat.completions.create(
            model=settings.triage.id,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )
        raw = response.choices[0].message.content
        results: list[dict] = json.loads(raw)
    except Exception:
        logger.warning(
            "triage_items: API call failed, returning all items unchanged", exc_info=True
        )
        return list(items)

    score_map = {r["item_id"]: r for r in results}
    relevant: list[Item] = []

    for item in items:
        result = score_map.get(item.id)
        if result is None:
            relevant.append(item)
            continue
        score: float = result.get("score", 0.0)
        summary: str | None = result.get("summary")
        status = "skipped" if score < 0.2 else "analyzed"
        conn.execute(
            "UPDATE items SET triage_score = ?, triage_summary = ?, status = ? WHERE id = ?",
            (score, summary, status, item.id),
        )
        if score >= 0.2:
            relevant.append(item)

    conn.commit()
    return relevant
