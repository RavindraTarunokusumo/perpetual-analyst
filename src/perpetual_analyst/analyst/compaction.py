"""Observation compaction: expire stale observations by importance/age. See SPEC §8."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import openai

from perpetual_analyst.analyst.agent import with_cache_control
from perpetual_analyst.analyst.memory import (
    get_active_observations,
    get_active_theses,
    get_dossier,
    update_dossier,
)
from perpetual_analyst.analyst.schemas import WeeklyReviewOutput
from perpetual_analyst.config import Settings
from perpetual_analyst.store.models import Topic

_WEEKLY_PROMPT_PATH = Path(__file__).parent / "prompts" / "weekly_review.md"


def expire_observations(conn: sqlite3.Connection, topic_id: int | None = None) -> int:
    """Mark active observations as expired based on importance and age thresholds.

    Rules:
    - importance 1: expires after 30 days
    - importance 2: expires after 90 days
    - importance 3: never expires
    - Only 'active' observations are candidates; 'promoted' and already 'expired' are untouched.

    Args:
        conn: SQLite connection with row_factory set (see db.py).
        topic_id: If provided, restrict expiry to this topic only.

    Returns:
        Number of rows changed.
    """
    topic_filter = "AND topic_id = :topic_id" if topic_id is not None else ""
    sql = f"""
        UPDATE observations
        SET status = 'expired'
        WHERE status = 'active'
          AND (
              (importance = 1 AND created_at < datetime('now', '-30 days'))
              OR
              (importance = 2 AND created_at < datetime('now', '-90 days'))
          )
          {topic_filter}
    """
    with conn:
        cur = conn.execute(sql, {"topic_id": topic_id} if topic_id is not None else {})
    return cur.rowcount


def run_weekly_review(
    topic: Topic,
    conn: sqlite3.Connection,
    client: openai.OpenAI,
    settings: Settings,
    dry_run: bool = False,
) -> WeeklyReviewOutput | None:
    """Call the model for a weekly compaction review on one topic.

    Builds a 2-message prompt (system = weekly_review.md, user = current memory snapshot),
    calls the model, and returns the parsed WeeklyReviewOutput.  Does NOT apply writes —
    call apply_weekly_review() for that.

    Args:
        topic: The topic to review.
        conn: SQLite connection.
        client: OpenAI-compatible client (pointed at OpenRouter).
        settings: App settings (model id, thinking flag).
        dry_run: If True, print messages and return None without calling the model.

    Returns:
        Parsed WeeklyReviewOutput, or None when dry_run=True.
    """
    system_prompt = _WEEKLY_PROMPT_PATH.read_text(encoding="utf-8").replace(
        "{topic_name}", topic.name
    )

    dossier = get_dossier(topic.id, conn) or "(no dossier yet)"
    observations = get_active_observations(topic.id, conn)
    theses = get_active_theses(topic.id, conn)

    obs_lines = (
        "\n".join(f"[obs:{o.id}] (importance {o.importance}) {o.content}" for o in observations)
        or "(no active observations)"
    )

    theses_lines = (
        "\n".join(f"[thesis:{t.id}] (confidence {t.confidence:.2f}) {t.statement}" for t in theses)
        or "(no active theses)"
    )

    user_content = (
        f"## Dossier\n{dossier}\n\n"
        f"## Active observations (importance-sorted)\n{obs_lines}\n\n"
        f"## Active theses\n{theses_lines}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    if dry_run:
        for msg in messages:
            print(f"[{msg['role'].upper()}]\n{msg['content']}\n{'=' * 60}")
        return None

    extra = {"thinking": {"type": "adaptive"}} if settings.analyst.thinking else {}
    # The weekly system prompt is stable across topics — cache it like the daily path.
    response = client.chat.completions.create(
        model=settings.analyst.id,
        messages=with_cache_control(messages),
        response_format={"type": "json_object"},
        extra_body=extra,
    )

    raw = response.choices[0].message.content or "{}"
    result = WeeklyReviewOutput.model_validate_json(raw)
    print(f"[compaction] topic={topic.slug} promoted={len(result.promoted_observation_ids)}")
    return result


def apply_weekly_review(
    topic_id: int,
    output: WeeklyReviewOutput,
    conn: sqlite3.Connection,
) -> None:
    """Apply weekly review writes transactionally.

    Rewrites the dossier (if output.dossier_rewrite is not None) and marks
    listed observation IDs as 'promoted', scoped to topic_id for safety.

    Args:
        topic_id: The topic these writes belong to.
        output: Parsed WeeklyReviewOutput from run_weekly_review().
        conn: SQLite connection — do not call conn.commit() here; with conn: handles it.
    """
    with conn:
        if output.dossier_rewrite is not None:
            update_dossier(topic_id, output.dossier_rewrite, conn)
        for obs_id in output.promoted_observation_ids:
            conn.execute(
                "UPDATE observations SET status='promoted' WHERE id=? AND topic_id=?",
                (obs_id, topic_id),
            )
