"""Merge per-topic sections into the daily report and write to DB. See SPEC §9."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import openai

from perpetual_analyst.analyst.schemas import NarrativeUpdate
from perpetual_analyst.config import Settings

_DIGEST_PROMPT_PATH = Path(__file__).parent.parent / "analyst" / "prompts" / "digest.md"
_DEFAULT_REPORTS_DIR = Path("data/reports")
_UNCLOSED_TAG = re.compile(r"<[^>]*$")


def _truncate_html(text: str, max_chars: int = 3000) -> str:
    """Truncate to max_chars, then strip any trailing unclosed HTML tag."""
    if len(text) <= max_chars:
        return text
    return _UNCLOSED_TAG.sub("", text[:max_chars])


def assemble_report(
    briefings: dict[str, NarrativeUpdate],
    date: str,
    conn: sqlite3.Connection,
    client: openai.OpenAI,
    settings: Settings,
    reports_dir: Path | None = None,
) -> int:
    """Assemble and store the daily report. Returns the report row ID.

    Steps:
    1. Build full_markdown by joining per-topic briefing sections.
    2. Generate digest_text via OpenRouter.
    3. Upsert into reports table.
    4. Write markdown file to reports_dir/brief-{date}.md.
    5. Return report row id.
    """
    if reports_dir is None:
        reports_dir = _DEFAULT_REPORTS_DIR

    parts: list[str] = [f"# Daily Report — {date}\n\n"]
    for slug, bundle in briefings.items():
        if bundle.nothing_significant:
            parts.append(f"## {slug}\n\nNothing significant.\n\n")
        else:
            parts.append(bundle.briefing_markdown.rstrip() + "\n\n")

    full_markdown = "".join(parts)

    digest_prompt = _DIGEST_PROMPT_PATH.read_text(encoding="utf-8")
    response = client.chat.completions.create(
        model=settings.analyst.id,
        messages=[
            {"role": "system", "content": digest_prompt},
            {"role": "user", "content": full_markdown},
        ],
    )
    digest_text = _truncate_html(response.choices[0].message.content or "")

    conn.execute(
        """INSERT INTO reports (report_date, full_markdown, digest_text, user_id)
           VALUES (?, ?, ?, 1)
           ON CONFLICT(report_date) DO UPDATE SET
               full_markdown = excluded.full_markdown,
               digest_text = excluded.digest_text""",
        (date, full_markdown, digest_text),
    )
    conn.commit()

    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / f"brief-{date}.md").write_text(full_markdown, encoding="utf-8")

    row = conn.execute("SELECT id FROM reports WHERE report_date = ?", (date,)).fetchone()
    return row["id"]
