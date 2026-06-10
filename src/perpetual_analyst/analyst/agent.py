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
from perpetual_analyst.config import Settings
from perpetual_analyst.store.models import Item, Topic

load_dotenv()

_system_prompt: str | None = None
_PROMPT_PATH = Path(__file__).parent / "prompts" / "analyst_system.md"


def load_system_prompt() -> str:
    global _system_prompt
    if _system_prompt is None:
        _system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    return _system_prompt


def make_client() -> openai.OpenAI:
    return openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )


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

    items_text = "\n\n".join(
        f"[item:{item.id}] {item.title or '(untitled)'}\n{item.raw_text or '(no text)'}"
        for item in items
    ) or "(no new items today)"

    user_content = (
        f"## Topic brief\n{topic.brief or '(no brief)'}\n\n"
        f"## Dossier\n{dossier}\n\n"
        f"## Active theses\n{theses_text}\n\n"
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
    used = response.usage.total_tokens if response.usage else len(str(messages)) // CHARS_PER_TOKEN
    print(f"[agent] topic={topic.slug} tokens={used} nothing_significant={result.nothing_significant}")

    apply_all_memory_writes(topic.id, result, conn)
    return result
