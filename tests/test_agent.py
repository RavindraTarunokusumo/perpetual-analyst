from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from perpetual_analyst.analyst.agent import (
    assemble_context,
    load_system_prompt,
    run_topic,
    with_cache_control,
)
from perpetual_analyst.analyst.memory import get_active_observations
from perpetual_analyst.config import ModelConfig, Settings
from perpetual_analyst.store.models import Topic


@pytest.fixture
def settings() -> Settings:
    return Settings(
        analyst=ModelConfig(id="anthropic/claude-opus-4-8", thinking=True),
        triage=ModelConfig(id="deepseek/deepseek-v4-flash", thinking=False),
    )


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
    mock_openrouter.chat.completions.create.assert_not_called()


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
    call_kwargs = mock_openrouter.chat.completions.create.call_args
    extra_body = call_kwargs.kwargs.get("extra_body", {})
    assert extra_body.get("thinking") == {"type": "adaptive"}


def test_assemble_context_includes_related_context_section(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings
) -> None:
    """assemble_context user message must contain Related prior observations section."""
    prompt = load_system_prompt()
    messages = assemble_context(sample_topic, sample_items, db, prompt, settings)
    user_content = messages[1]["content"]
    assert "## Related prior observations" in user_content
    assert "## Related prior items" in user_content


def test_run_topic_no_thinking_when_disabled(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, mock_openrouter: MagicMock
) -> None:
    settings_no_thinking = Settings(
        analyst=ModelConfig(id="some-model", thinking=False),
        triage=ModelConfig(id="deepseek/deepseek-v4-flash", thinking=False),
    )
    run_topic(sample_topic, sample_items, db, mock_openrouter, settings_no_thinking)
    call_kwargs = mock_openrouter.chat.completions.create.call_args
    extra_body = call_kwargs.kwargs.get("extra_body", {})
    assert "thinking" not in extra_body


def test_assemble_context_stale_thesis_marker(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings
) -> None:
    """A stale active thesis (updated_at -40 days) must produce '(stale)' in the user message."""
    cur = db.execute(
        "INSERT INTO theses (topic_id, statement, confidence, status) VALUES (?, ?, ?, 'active')",
        (sample_topic.id, "Old stale thesis", 0.6),
    )
    thesis_id = cur.lastrowid
    db.execute(
        "UPDATE theses SET updated_at = datetime('now', '-40 days') WHERE id = ?",
        (thesis_id,),
    )
    db.commit()
    prompt = load_system_prompt()
    messages = assemble_context(sample_topic, sample_items, db, prompt, settings)
    assert "(stale)" in messages[1]["content"]


def test_assemble_context_thesis_history_heading(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings
) -> None:
    """The assembled user message must contain the '## Thesis history' heading."""
    prompt = load_system_prompt()
    messages = assemble_context(sample_topic, sample_items, db, prompt, settings)
    assert "## Thesis history" in messages[1]["content"]


def test_assemble_context_stable_prefix_before_volatile(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings
) -> None:
    """Stable sections must appear before volatile sections in the user message."""
    prompt = load_system_prompt()
    messages = assemble_context(sample_topic, sample_items, db, prompt, settings)
    user_content = messages[1]["content"]
    assert user_content.index("## Topic brief") < user_content.index(
        "## Yesterday's report section"
    )
    assert user_content.index("## Active theses") < user_content.index("## Today's items")


def test_with_cache_control_marks_system() -> None:
    """with_cache_control converts the system message content to a list with cache_control."""
    original_system = "You are a helpful analyst."
    original_user = "Analyse this."
    messages = [
        {"role": "system", "content": original_system},
        {"role": "user", "content": original_user},
    ]
    result = with_cache_control(messages)
    # System message: content is now a list
    sys_msg = result[0]
    assert isinstance(sys_msg["content"], list)
    assert len(sys_msg["content"]) == 1
    part = sys_msg["content"][0]
    assert part["type"] == "text"
    assert part["text"] == original_system
    assert part["cache_control"] == {"type": "ephemeral"}
    # User message: unchanged
    user_msg = result[1]
    assert user_msg["content"] == original_user
    # Originals untouched
    assert messages[0]["content"] == original_system
    assert messages[1]["content"] == original_user


def test_run_topic_sends_cache_control(
    db: sqlite3.Connection,
    sample_topic: Topic,
    sample_items,
    settings: Settings,
    mock_openrouter: MagicMock,
) -> None:
    """run_topic must pass the system message with a cache_control breakpoint to the API."""
    run_topic(sample_topic, sample_items, db, mock_openrouter, settings, dry_run=False)
    call_kwargs = mock_openrouter.chat.completions.create.call_args.kwargs
    api_messages = call_kwargs["messages"]
    sys_msg = next(m for m in api_messages if m["role"] == "system")
    assert isinstance(sys_msg["content"], list)
    part = sys_msg["content"][0]
    assert part.get("cache_control") == {"type": "ephemeral"}
