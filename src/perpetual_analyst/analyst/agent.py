from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import openai
from dotenv import load_dotenv

from perpetual_analyst.analyst.memory import (
    CHARS_PER_TOKEN,
    apply_all_memory_writes,
    build_memory_context,
    get_active_theses,
    get_dossier,
)
from perpetual_analyst.analyst.schemas import TopicAnalysis
from perpetual_analyst.analyst.theses import get_stale_theses
from perpetual_analyst.config import Settings
from perpetual_analyst.retrieval.search import related_items, related_observations
from perpetual_analyst.store.models import Item, Topic

load_dotenv()

_system_prompt: str | None = None
_PROMPT_PATH = Path(__file__).parent / "prompts" / "analyst_system.md"
_ITEM_TEXT_LIMIT = 3000  # chars per item; caps large PDFs without truncating short items
_RELATED_OBS_CHARS = 200  # one-line truncation for related-context entries


def load_system_prompt() -> str:
    global _system_prompt
    if _system_prompt is None:
        _system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    return _system_prompt


def make_client() -> openai.OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set — add it to .env or set it in the environment"
        )
    return openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


def _render_item_block(
    item: Item, topic_id: int, conn: sqlite3.Connection, exclude_ids: list[int]
) -> str:
    parts = [f"[item:{item.id}] {item.title or '(untitled)'}"]
    if item.triage_summary:
        parts.append(f"Triage summary: {item.triage_summary}")
    parts.append((item.raw_text or "(no text)")[:_ITEM_TEXT_LIMIT])

    query_text = f"{item.title or ''} {item.triage_summary or ''}".strip()
    if query_text:
        context_lines = [
            f"  [obs:{o.id}] {o.content[:_RELATED_OBS_CHARS]}"
            for o in related_observations(query_text, topic_id, conn)
        ]
        context_lines += [
            f"  [item:{r.id}] {r.title or '(untitled)'}"
            for r in related_items(query_text, topic_id, conn, exclude_ids=exclude_ids)
        ]
        if context_lines:
            parts.append("Related prior context:\n" + "\n".join(context_lines))
    return "\n".join(parts)


def assemble_context(
    topic: Topic,
    items: list[Item],
    conn: sqlite3.Connection,
    system_prompt: str,
    settings: Settings,
) -> list[dict]:
    dossier = get_dossier(topic.id, conn) or "(no dossier yet)"
    theses = get_active_theses(topic.id, conn)
    observations_text = build_memory_context(topic.id, conn, token_budget=3000)

    row = conn.execute(
        "SELECT full_markdown FROM reports "
        "WHERE report_date < date('now') ORDER BY report_date DESC LIMIT 1"
    ).fetchone()
    yesterday_section = row["full_markdown"] if row else "(no prior report)"

    theses_text = (
        "\n".join(f"[thesis:{t.id}] (confidence {t.confidence:.2f}) {t.statement}" for t in theses)
        or "(no active theses)"
    )

    stale = get_stale_theses(topic.id, conn)
    stale_text = (
        "\n".join(
            f"[thesis:{t.id}] (last touched {t.updated_at or t.created_at}) {t.statement}"
            for t in stale
        )
        or "(none)"
    )

    exclude_ids = [item.id for item in items]
    items_text = (
        "\n\n".join(_render_item_block(item, topic.id, conn, exclude_ids) for item in items)
        or "(no new items today)"
    )

    user_content = (
        f"## Topic brief\n{topic.brief or '(no brief)'}\n\n"
        f"## Dossier\n{dossier}\n\n"
        f"## Active theses\n{theses_text}\n\n"
        f"## Stale theses — revisit or retire\n{stale_text}\n\n"
        f"## Yesterday's report section\n{yesterday_section}\n\n"
        f"## Prior observations\n{observations_text or '(no prior observations)'}\n\n"
        f"## Today's items\n{items_text}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def run_topic(
    topic: Topic,
    items: list[Item],
    conn: sqlite3.Connection,
    client: openai.OpenAI,
    settings: Settings,
    dry_run: bool = False,
) -> TopicAnalysis | None:
    system_prompt = load_system_prompt()
    messages = assemble_context(topic, items, conn, system_prompt, settings)

    if dry_run:
        for msg in messages:
            print(f"[{msg['role'].upper()}]\n{msg['content']}\n{'=' * 60}")
        return None

    extra = {"thinking": {"type": "adaptive"}} if settings.analyst.thinking else {}
    response = client.beta.chat.completions.parse(
        model=settings.analyst.id,
        messages=messages,
        response_format=TopicAnalysis,
        extra_body=extra,
    )

    result: TopicAnalysis = response.parsed
    used = (
        response.usage.total_tokens
        if response.usage
        else sum(len(m["content"]) for m in messages) // CHARS_PER_TOKEN
    )
    print(
        f"[agent] topic={topic.slug} tokens={used} nothing_significant={result.nothing_significant}"
    )

    apply_all_memory_writes(topic.id, result, conn)
    return result
