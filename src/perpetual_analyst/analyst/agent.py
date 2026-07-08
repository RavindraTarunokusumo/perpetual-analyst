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
    get_dossier,
)
from perpetual_analyst.analyst.schemas import TopicAnalysis
from perpetual_analyst.analyst.theses import render_thesis_fragment, render_thesis_trail
from perpetual_analyst.config import Settings
from perpetual_analyst.retrieval.search import related_items, related_observations
from perpetual_analyst.store.models import Item, Topic

load_dotenv()

_system_prompt: str | None = None
_PROMPT_PATH = Path(__file__).parent / "prompts" / "analyst_system.md"
_ITEM_TEXT_LIMIT = 3000  # chars per item; caps large PDFs without truncating short items


def load_system_prompt() -> str:
    global _system_prompt
    if _system_prompt is None:
        _system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    return _system_prompt


def make_client(provider: str = "openrouter") -> openai.OpenAI:
    if provider in {"openrouter", "openrouter_web"}:
        api_key_env = "OPENROUTER_API_KEY"
        base_url = "https://openrouter.ai/api/v1"
    elif provider == "perplexity":
        api_key_env = "PERPLEXITY_API_KEY"
        base_url = "https://api.perplexity.ai"
    else:
        raise RuntimeError(f"Unsupported client provider: {provider}")

    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(
            f"{api_key_env} is not set — add it to .env or set it in the environment"
        )
    return openai.OpenAI(
        base_url=base_url,
        api_key=api_key,
    )


def assemble_context(
    topic: Topic,
    items: list[Item],
    conn: sqlite3.Connection,
    system_prompt: str,
    settings: Settings,
) -> list[dict]:
    dossier = get_dossier(topic.id, conn) or "(no dossier yet)"
    observations_text = build_memory_context(topic.id, conn, token_budget=3000)

    row = conn.execute(
        "SELECT full_markdown FROM reports "
        "WHERE report_date < date('now') ORDER BY report_date DESC LIMIT 1"
    ).fetchone()
    yesterday_section = row["full_markdown"] if row else "(no prior report)"

    theses_text = render_thesis_fragment(topic.id, conn)
    thesis_trail_text = render_thesis_trail(topic.id, conn)

    items_text = (
        "\n\n".join(
            f"[item:{item.id}] {item.title or '(untitled)'}\n"
            f"{(item.raw_text or '(no text)')[:_ITEM_TEXT_LIMIT]}"
            for item in items
        )
        or "(no new items today)"
    )

    # Related prior context via FTS5 search
    query_text = " ".join(item.raw_text[:200] for item in items[:3] if item.raw_text)
    if query_text:
        rel_obs = related_observations(query_text, topic.id, conn, k=5)
        rel_items = related_items(query_text, topic.id, conn, k=3)
        rel_obs_text = "\n".join(f"[obs:{o.id}] {o.content}" for o in rel_obs) or "(none)"
        rel_items_text = (
            "\n".join(f"[item:{i.id}] {i.title or '(untitled)'}" for i in rel_items) or "(none)"
        )
    else:
        rel_obs_text = "(none)"
        rel_items_text = "(none)"

    # Stable prefix first (cache-friendly), volatile content last
    user_content = (
        f"## Topic brief\n{topic.brief or '(no brief)'}\n\n"
        f"## Dossier\n{dossier}\n\n"
        f"## Active theses\n{theses_text}\n\n"
        f"## Thesis history\n{thesis_trail_text}\n\n"
        f"## Yesterday's report section\n{yesterday_section}\n\n"
        f"## Prior observations\n{observations_text or '(no prior observations)'}\n\n"
        f"## Related prior observations\n{rel_obs_text}\n\n"
        f"## Related prior items\n{rel_items_text}\n\n"
        f"## Today's items\n{items_text}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def with_cache_control(messages: list[dict]) -> list[dict]:
    """Return a copy of messages with an ephemeral cache_control breakpoint on the system
    prompt, so OpenRouter/Anthropic can cache the stable prefix across runs.

    The OpenAI-style string content is converted to a single text content-block carrying
    cache_control. Non-system messages are passed through unchanged. Shared by the daily
    (run_topic) and weekly (run_weekly_review) call paths.
    """
    result = []
    for msg in messages:
        if msg["role"] == "system":
            result.append(
                {
                    **msg,
                    "content": [
                        {
                            "type": "text",
                            "text": msg["content"],
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }
            )
        else:
            result.append(dict(msg))
    return result


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
    api_messages = with_cache_control(messages)
    response = client.chat.completions.create(
        model=settings.analyst.id,
        messages=api_messages,
        response_format={"type": "json_object"},
        extra_body=extra,
    )

    raw = response.choices[0].message.content or "{}"
    result = TopicAnalysis.model_validate_json(raw)
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
