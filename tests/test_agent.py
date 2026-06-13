from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from perpetual_analyst.analyst.agent import assemble_context, load_system_prompt, run_topic
from perpetual_analyst.analyst.memory import get_active_observations
from perpetual_analyst.config import ModelConfig, Settings
from perpetual_analyst.store.models import Item, Topic


def test_load_system_prompt_returns_string() -> None:
    prompt = load_system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 100
    assert "nothing_significant" in prompt


def test_assemble_context_returns_two_messages(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings
) -> None:
    prompt = load_system_prompt()
    messages = assemble_context(sample_topic, sample_items, db, prompt, settings)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_assemble_context_system_is_prompt(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings
) -> None:
    prompt = load_system_prompt()
    messages = assemble_context(sample_topic, sample_items, db, prompt, settings)
    assert messages[0]["content"] == prompt


def test_assemble_context_includes_item_tags(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings
) -> None:
    prompt = load_system_prompt()
    messages = assemble_context(sample_topic, sample_items, db, prompt, settings)
    user_content = messages[1]["content"]
    for item in sample_items:
        assert f"[item:{item.id}]" in user_content


def test_assemble_context_includes_topic_brief(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings
) -> None:
    prompt = load_system_prompt()
    messages = assemble_context(sample_topic, sample_items, db, prompt, settings)
    assert sample_topic.brief in messages[1]["content"]


def test_run_topic_dry_run_returns_none(
    db: sqlite3.Connection,
    sample_topic: Topic,
    sample_items,
    settings: Settings,
    mock_openrouter: MagicMock,
) -> None:
    result = run_topic(sample_topic, sample_items, db, mock_openrouter, settings, dry_run=True)
    assert result is None
    mock_openrouter.beta.chat.completions.parse.assert_not_called()


def test_run_topic_dry_run_prints_messages(
    db: sqlite3.Connection,
    sample_topic: Topic,
    sample_items,
    settings: Settings,
    mock_openrouter: MagicMock,
    capsys,
) -> None:
    run_topic(sample_topic, sample_items, db, mock_openrouter, settings, dry_run=True)
    captured = capsys.readouterr()
    assert "SYSTEM" in captured.out
    assert "USER" in captured.out


def test_run_topic_commits_memory_writes(
    db: sqlite3.Connection,
    sample_topic: Topic,
    sample_items,
    settings: Settings,
    mock_openrouter: MagicMock,
) -> None:
    run_topic(sample_topic, sample_items, db, mock_openrouter, settings, dry_run=False)
    observations = get_active_observations(sample_topic.id, db)
    assert len(observations) == 1
    assert observations[0].content == "Test signal observed."


def test_run_topic_passes_thinking_when_configured(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, mock_openrouter: MagicMock
) -> None:
    settings_thinking = Settings(
        analyst=ModelConfig(id="anthropic/claude-opus-4-8", thinking=True),
        triage=ModelConfig(id="deepseek/deepseek-v4-flash", thinking=False),
    )
    run_topic(sample_topic, sample_items, db, mock_openrouter, settings_thinking)
    call_kwargs = mock_openrouter.beta.chat.completions.parse.call_args
    extra_body = call_kwargs.kwargs.get("extra_body", {})
    assert extra_body.get("thinking") == {"type": "adaptive"}


def test_run_topic_no_thinking_when_disabled(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, mock_openrouter: MagicMock
) -> None:
    settings_no_thinking = Settings(
        analyst=ModelConfig(id="some-model", thinking=False),
        triage=ModelConfig(id="deepseek/deepseek-v4-flash", thinking=False),
    )
    run_topic(sample_topic, sample_items, db, mock_openrouter, settings_no_thinking)
    call_kwargs = mock_openrouter.beta.chat.completions.parse.call_args
    extra_body = call_kwargs.kwargs.get("extra_body", {})
    assert "thinking" not in extra_body


def test_assemble_context_flags_stale_theses(db, sample_topic, settings):
    db.execute(
        "INSERT INTO theses (topic_id, statement, confidence, status, created_at, updated_at)"
        " VALUES (?, 'Dusty thesis', 0.5, 'active',"
        " datetime('now', '-45 days'), datetime('now', '-40 days'))",
        (sample_topic.id,),
    )
    db.commit()
    messages = assemble_context(sample_topic, [], db, "system prompt", settings)
    user_content = messages[1]["content"]
    assert "## Stale theses — revisit or retire" in user_content
    assert "Dusty thesis" in user_content


def test_assemble_context_stale_section_present_when_empty(db, sample_topic, settings):
    messages = assemble_context(sample_topic, [], db, "system prompt", settings)
    user_content = messages[1]["content"]
    assert "## Stale theses — revisit or retire\n(none)" in user_content


def test_assemble_context_attaches_related_prior_context(db, sample_topic, sample_source, settings):
    db.execute(
        "INSERT INTO topic_sources (topic_id, source_id) VALUES (?, ?)",
        (sample_topic.id, sample_source),
    )
    db.execute(
        "INSERT INTO observations (topic_id, kind, content, importance, status)"
        " VALUES (?, 'signal', 'GPU export controls tightened in May', 2, 'active')",
        (sample_topic.id,),
    )
    cur = db.execute(
        "INSERT INTO items (source_id, content_hash, title, raw_text, triage_summary)"
        " VALUES (?, 'hash_new', 'Export controls on GPUs expanded',"
        " 'Today the export controls were expanded.', 'GPU export controls expanded again')",
        (sample_source,),
    )
    db.commit()
    row = db.execute("SELECT * FROM items WHERE id = ?", (cur.lastrowid,)).fetchone()
    new_item = Item.from_row(row)

    messages = assemble_context(sample_topic, [new_item], db, "system prompt", settings)
    user_content = messages[1]["content"]
    assert "Related prior context:" in user_content
    assert "[obs:" in user_content
    assert "GPU export controls tightened in May" in user_content


def test_assemble_context_no_related_context_when_nothing_matches(
    db, sample_topic, sample_items, settings
):
    messages = assemble_context(sample_topic, sample_items, db, "system prompt", settings)
    assert "Related prior context:" not in messages[1]["content"]


def test_run_topic_marks_items_analyzed(db, sample_topic, sample_items, settings, mock_openrouter):
    result = run_topic(sample_topic, sample_items, db, mock_openrouter, settings)
    assert result is not None
    statuses = [
        r["status"]
        for r in db.execute(
            "SELECT status FROM items WHERE id IN (?, ?, ?)",
            [i.id for i in sample_items],
        ).fetchall()
    ]
    assert statuses == ["analyzed", "analyzed", "analyzed"]


def test_dry_run_does_not_mark_items(db, sample_topic, sample_items, settings, mock_openrouter):
    run_topic(sample_topic, sample_items, db, mock_openrouter, settings, dry_run=True)
    statuses = [r["status"] for r in db.execute("SELECT status FROM items").fetchall()]
    assert all(s == "new" for s in statuses)


def test_memory_writes_and_analyzed_marking_are_atomic(
    db, sample_topic, sample_items, settings, mock_openrouter, monkeypatch
):
    from perpetual_analyst.analyst import memory

    def _boom(*args, **kwargs):
        raise sqlite3.OperationalError("simulated failure")

    monkeypatch.setattr(memory, "update_dossier", _boom)
    parsed = mock_openrouter.beta.chat.completions.parse.return_value.choices[0].message.parsed
    parsed.dossier_edits = "new dossier"

    with pytest.raises(sqlite3.OperationalError):
        run_topic(sample_topic, sample_items, db, mock_openrouter, settings)

    assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
    assert all(r["status"] == "new" for r in db.execute("SELECT status FROM items").fetchall())


def test_run_topic_empty_items_makes_no_api_call(db, sample_topic, settings, mock_openrouter):
    result = run_topic(sample_topic, [], db, mock_openrouter, settings)
    assert result is not None
    assert result.nothing_significant is True
    assert mock_openrouter.beta.chat.completions.parse.call_count == 0
    assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0


def test_run_topic_empty_items_dry_run_still_returns_none(
    db, sample_topic, settings, mock_openrouter
):
    result = run_topic(sample_topic, [], db, mock_openrouter, settings, dry_run=True)
    assert result is None
    assert mock_openrouter.beta.chat.completions.parse.call_count == 0
