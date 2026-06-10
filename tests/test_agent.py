from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from perpetual_analyst.analyst.agent import assemble_context, load_system_prompt, run_topic
from perpetual_analyst.analyst.memory import get_active_observations, get_dossier, get_active_theses
from perpetual_analyst.analyst.schemas import TopicAnalysis
from perpetual_analyst.config import Settings, ModelConfig
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
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings,
    mock_openrouter: MagicMock
) -> None:
    result = run_topic(sample_topic, sample_items, db, mock_openrouter, settings, dry_run=True)
    assert result is None
    mock_openrouter.beta.chat.completions.parse.assert_not_called()


def test_run_topic_dry_run_prints_messages(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings,
    mock_openrouter: MagicMock, capsys
) -> None:
    run_topic(sample_topic, sample_items, db, mock_openrouter, settings, dry_run=True)
    captured = capsys.readouterr()
    assert "SYSTEM" in captured.out
    assert "USER" in captured.out


def test_run_topic_commits_memory_writes(
    db: sqlite3.Connection, sample_topic: Topic, sample_items, settings: Settings,
    mock_openrouter: MagicMock
) -> None:
    run_topic(sample_topic, sample_items, db, mock_openrouter, settings, dry_run=False)
    observations = get_active_observations(sample_topic.id, db)
    assert len(observations) == 1
    assert observations[0].content == "Test signal observed."


def test_run_topic_passes_thinking_when_configured(
    db: sqlite3.Connection, sample_topic: Topic, sample_items,
    mock_openrouter: MagicMock
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
    db: sqlite3.Connection, sample_topic: Topic, sample_items,
    mock_openrouter: MagicMock
) -> None:
    settings_no_thinking = Settings(
        analyst=ModelConfig(id="some-model", thinking=False),
        triage=ModelConfig(id="deepseek/deepseek-v4-flash", thinking=False),
    )
    run_topic(sample_topic, sample_items, db, mock_openrouter, settings_no_thinking)
    call_kwargs = mock_openrouter.beta.chat.completions.parse.call_args
    extra_body = call_kwargs.kwargs.get("extra_body", {})
    assert "thinking" not in extra_body
