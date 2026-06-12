"""Merge per-topic sections into the daily report; one digest call per day. See SPEC §9."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import openai

from perpetual_analyst.analyst.schemas import DigestOutput, TopicAnalysis
from perpetual_analyst.analyst.theses import render_thesis_fragment
from perpetual_analyst.config import Settings
from perpetual_analyst.report.render import render_citations
from perpetual_analyst.store.models import Thesis, ThesisUpdate, Topic

_DIGEST_PROMPT_PATH = Path(__file__).parent.parent / "analyst" / "prompts" / "digest.md"
_FALLBACK_DIGEST_CHARS = 3000


def _todays_thesis_pairs(
    topic_id: int, report_date: str, conn: sqlite3.Connection
) -> list[tuple[Thesis, ThesisUpdate]]:
    updates = conn.execute(
        """SELECT u.* FROM thesis_updates u
           JOIN theses t ON t.id = u.thesis_id
           WHERE t.topic_id = ? AND date(u.created_at) = ?
           ORDER BY u.id""",
        (topic_id, report_date),
    ).fetchall()
    pairs = []
    for update_row in updates:
        thesis_row = conn.execute(
            "SELECT * FROM theses WHERE id = ?", (update_row["thesis_id"],)
        ).fetchone()
        pairs.append((Thesis.from_row(thesis_row), ThesisUpdate.from_row(update_row)))
    return pairs


def _generate_digest(
    sections_text: str, client: openai.OpenAI, settings: Settings
) -> DigestOutput | None:
    try:
        extra = {"thinking": {"type": "adaptive"}} if settings.analyst.thinking else {}
        response = client.beta.chat.completions.parse(
            model=settings.analyst.id,
            messages=[
                {"role": "system", "content": _DIGEST_PROMPT_PATH.read_text(encoding="utf-8")},
                {"role": "user", "content": sections_text},
            ],
            response_format=DigestOutput,
            extra_body=extra,
        )
        return response.choices[0].message.parsed
    except Exception as exc:
        print(f"[report] digest call failed: {type(exc).__name__}")
        return None


def assemble_report(
    topic_results: list[tuple[Topic, TopicAnalysis]],
    conn: sqlite3.Connection,
    client: openai.OpenAI,
    settings: Settings,
    report_date: str,
) -> tuple[str, str]:
    """Returns (digest_text, full_markdown). One digest LLM call; mechanical fallback."""
    topic_blocks: list[str] = []
    for topic, analysis in topic_results:
        lines = [f"## Topic: {topic.name}", ""]
        if analysis.nothing_significant:
            lines.append(f"*{topic.name}: nothing significant today.*")
        else:
            lines.append(analysis.report_section_markdown)
            fragment = render_thesis_fragment(_todays_thesis_pairs(topic.id, report_date, conn))
            if fragment:
                lines += ["", fragment]
        topic_blocks.append("\n".join(lines))

    sections_text = "\n\n".join(topic_blocks)
    digest = _generate_digest(sections_text, client, settings)

    parts = [f"# Daily Intelligence Brief — {report_date}", ""]
    if digest is not None and digest.executive_summary:
        parts += ["## Executive summary", "", digest.executive_summary, ""]
    parts.append(sections_text)

    open_questions = [q for _, a in topic_results for q in a.open_questions]
    if open_questions:
        parts += ["", "## Open questions", ""] + [f"- {q}" for q in open_questions]
    watch_next = [w for _, a in topic_results for w in a.watch_next]
    if watch_next:
        parts += ["", "## Things to watch next", ""] + [f"- {w}" for w in watch_next]

    full_markdown = render_citations("\n".join(parts), conn)
    digest_text = (
        digest.digest_text if digest is not None else sections_text[:_FALLBACK_DIGEST_CHARS]
    )
    return digest_text, full_markdown


def persist_report(
    report_date: str,
    digest_text: str,
    full_markdown: str,
    conn: sqlite3.Connection,
    reports_dir: str = "data/reports",
) -> int:
    """INSERT (UNIQUE report_date raises loudly on a bypassed per-day guard) + write file."""
    cur = conn.execute(
        "INSERT INTO reports (user_id, report_date, digest_text, full_markdown)"
        " VALUES (NULL, ?, ?, ?)",
        (report_date, digest_text, full_markdown),
    )
    conn.commit()
    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"brief-{report_date}.md").write_text(full_markdown, encoding="utf-8")
    return cur.lastrowid
