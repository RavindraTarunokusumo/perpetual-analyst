"""Relevance triage pass via the configured cheap model (settings.triage.id). See SPEC §4.

Protects the analyst's context window: the expensive model sees 10-30 distilled
items, not 200 raw articles. This is a function, not an agent (Invariant 1).
"""

from __future__ import annotations

import re
import sqlite3

import openai
from pydantic import BaseModel, Field, TypeAdapter

from perpetual_analyst.config import Settings
from perpetual_analyst.store.models import Item

CHUNK_SIZE = 20
SKIP_THRESHOLD = 0.2
_EXCERPT_CHARS = 1500

_PROMPT_TEMPLATE = """You are a relevance triage filter for an intelligence analyst.

Topic brief:
{brief}

Score each item below for relevance to the topic brief (0.0 = irrelevant,
1.0 = essential reading) and write a 2-line summary of each.

Items:
{items}

Return ONLY a JSON array, one object per item, no other text:
[{{"item_id": <int>, "score": <float 0-1>, "summary": "<2-line summary>"}}]"""


class TriageResult(BaseModel):
    item_id: int
    score: float = Field(ge=0.0, le=1.0)
    summary: str


_RESULTS = TypeAdapter(list[TriageResult])
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip())


def _format_items(items: list[Item]) -> str:
    blocks = []
    for item in items:
        excerpt = (item.raw_text or "")[:_EXCERPT_CHARS]
        blocks.append(f"item_id={item.id}\ntitle: {item.title or '(untitled)'}\n{excerpt}")
    return "\n\n".join(blocks)


def _triage_chunk(
    chunk: list[Item],
    topic_brief: str,
    client: openai.OpenAI,
    settings: Settings,
) -> list[TriageResult]:
    prompt = _PROMPT_TEMPLATE.format(brief=topic_brief, items=_format_items(chunk))
    for _ in range(2):
        response = client.chat.completions.create(
            model=settings.triage.id,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or ""
        try:
            return _RESULTS.validate_json(_strip_fences(text))
        except Exception as exc:
            prompt = (
                f"{prompt}\n\nYour previous reply failed validation ({exc}). "
                "Return ONLY the JSON array."
            )
    print(f"[triage] chunk of {len(chunk)} items failed validation twice; left untriaged")
    return []


def triage_items(
    items: list[Item],
    topic_brief: str,
    client: openai.OpenAI,
    settings: Settings,
    conn: sqlite3.Connection,
) -> list[TriageResult]:
    """Score + summarize items in chunks; writes triage columns and skip-status to DB."""
    known_ids = {item.id for item in items}
    accepted: list[TriageResult] = []
    for start in range(0, len(items), CHUNK_SIZE):
        chunk = items[start : start + CHUNK_SIZE]
        for result in _triage_chunk(chunk, topic_brief, client, settings):
            if result.item_id not in known_ids:
                continue
            conn.execute(
                "UPDATE items SET triage_score = ?, triage_summary = ?,"
                " status = CASE WHEN ? < ? THEN 'skipped' ELSE status END"
                " WHERE id = ?",
                (result.score, result.summary, result.score, SKIP_THRESHOLD, result.item_id),
            )
            accepted.append(result)
        conn.commit()
    return accepted
