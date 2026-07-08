"""Weekly source-discovery run: mine outbound domains and propose new candidates. See SPEC §11."""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import openai

from perpetual_analyst.analyst.memory import get_dossier
from perpetual_analyst.analyst.schemas import DiscoveryOutput
from perpetual_analyst.config import Settings
from perpetual_analyst.store.models import Topic

_DISCOVERY_PROMPT_PATH = Path(__file__).parent / "prompts" / "discovery.md"


def _extract_json_object(raw: str) -> str:
    """Return the JSON object substring from a model response.

    The OpenRouter web-search plugin does not honor response_format=json_object — the
    web-augmented model often prepends prose (or wraps the JSON in ``` fences) before the
    object. Strip fences and slice from the first '{' to the last '}' so model_validate_json
    sees clean JSON. Falls back to the original string if no object is found.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text


def _domain(url: str | None) -> str | None:
    """Extract bare domain from a URL, stripping a leading www. prefix."""
    if not url:
        return None
    netloc = urlparse(url).netloc
    if not netloc:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


def mine_outbound_domains(
    topic_id: int, conn: sqlite3.Connection, limit: int = 10
) -> list[tuple[str, int]]:
    """Domains of cited items for this topic's sources, ranked by citation frequency (desc).

    Joins citations → items → topic_sources to find items whose source belongs to this topic,
    extracts the bare domain from items.url, and returns the top `limit` domains sorted by
    citation count descending. Rows with NULL or empty url are skipped.
    """
    rows = conn.execute(
        """
        SELECT i.url
        FROM citations c
        JOIN items i ON i.id = c.item_id
        JOIN topic_sources ts ON ts.source_id = i.source_id
        WHERE ts.topic_id = ?
          AND i.url IS NOT NULL
          AND i.url != ''
        """,
        (topic_id,),
    ).fetchall()

    domains = [d for row in rows if (d := _domain(row["url"]))]
    return Counter(domains).most_common(limit)


DEFAULT_PERPLEXITY_MODEL = "sonar-pro"


def web_search_extra(provider: str = "openrouter_web") -> dict:
    """Discovery provider extra_body config (the provider seam).

    OpenRouter web search uses the plugin extra body. Perplexity is already a
    search-grounded provider and must not receive the OpenRouter plugin payload.
    """
    if provider == "openrouter_web":
        return {"plugins": [{"id": "web", "max_results": 5}]}
    if provider == "perplexity":
        return {}
    raise RuntimeError(f"Unsupported discovery provider: {provider}")


def discover_sources(
    topic: Topic,
    conn: sqlite3.Connection,
    client: openai.OpenAI,
    settings: Settings,
    dry_run: bool = False,
) -> DiscoveryOutput | None:
    """Run a weekly source-discovery pass for one topic.

    Builds a 2-message prompt (system = discovery.md, user = topic context + mined domains),
    calls the model with a web-search plugin, and stores each proposed candidate into
    source_candidates with status 'pending'. Returns the parsed DiscoveryOutput.

    Args:
        topic: The topic to discover sources for.
        conn: SQLite connection.
        client: OpenAI-compatible client (pointed at OpenRouter).
        settings: App settings (model id, thinking flag).
        dry_run: If True, print messages and return None without calling the model.

    Returns:
        Parsed DiscoveryOutput, or None when dry_run=True.
    """
    system_prompt = _DISCOVERY_PROMPT_PATH.read_text(encoding="utf-8").replace(
        "{topic_name}", topic.name
    )

    dossier = get_dossier(topic.id, conn) or "(no dossier yet)"
    mined = mine_outbound_domains(topic.id, conn)
    domains_text = "\n".join(f"- {d} ({n} citations)" for d, n in mined) or "(none yet)"

    user_content = (
        f"## Topic brief\n{topic.brief or '(no brief)'}\n\n"
        f"## Dossier\n{dossier}\n\n"
        f"## Domains already supplying material\n{domains_text}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    if dry_run:
        for msg in messages:
            print(f"[{msg['role'].upper()}]\n{msg['content']}\n{'=' * 60}")
        return None

    provider = settings.discovery.provider
    extra = web_search_extra(provider)
    if provider == "openrouter_web" and settings.analyst.thinking:
        extra["thinking"] = {"type": "adaptive"}
    model = settings.discovery.model
    if model is None:
        model = DEFAULT_PERPLEXITY_MODEL if provider == "perplexity" else settings.analyst.id

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        extra_body=extra,
    )

    raw = response.choices[0].message.content or "{}"
    result = DiscoveryOutput.model_validate_json(_extract_json_object(raw))
    print(f"[discovery] topic={topic.slug} candidates={len(result.candidates)}")

    with conn:
        for candidate in result.candidates:
            domain = candidate.domain or _domain(candidate.url) or ""
            conn.execute(
                """INSERT OR IGNORE INTO source_candidates
                       (topic_id, url, domain, rationale, status)
                   VALUES (?, ?, ?, ?, 'pending')""",
                (topic.id, candidate.url, domain, candidate.rationale),
            )

    return result
