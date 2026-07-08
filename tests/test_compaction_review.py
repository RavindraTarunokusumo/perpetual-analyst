"""Tests for weekly review compaction: run_weekly_review + apply_weekly_review. See SPEC §8."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from perpetual_analyst.analyst.compaction import apply_weekly_review, run_weekly_review
from perpetual_analyst.analyst.memory import (
    get_dossier,
    insert_observation,
)
from perpetual_analyst.analyst.schemas import WeeklyReviewOutput
from perpetual_analyst.config import ModelConfig, Settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings() -> Settings:
    return Settings(
        analyst=ModelConfig(id="anthropic/claude-3-haiku", thinking=False),
        triage=ModelConfig(id="anthropic/claude-3-haiku", thinking=False),
    )


def _make_weekly_client(output: WeeklyReviewOutput) -> MagicMock:
    """Build a mock OpenAI client whose create() returns the given WeeklyReviewOutput as JSON."""
    message_mock = MagicMock()
    message_mock.content = output.model_dump_json()

    choice_mock = MagicMock()
    choice_mock.message = message_mock

    response_mock = MagicMock()
    response_mock.choices = [choice_mock]
    response_mock.usage = None

    client_mock = MagicMock()
    client_mock.chat.completions.create.return_value = response_mock
    return client_mock


def _insert_obs(topic_id: int, conn: sqlite3.Connection, content: str, importance: int = 2) -> int:
    return insert_observation(topic_id, "signal", content, importance, conn)


# ---------------------------------------------------------------------------
# dry_run returns None without calling the model
# ---------------------------------------------------------------------------


def test_dry_run_returns_none_no_api_call(db, sample_topic, capsys):
    client = _make_weekly_client(WeeklyReviewOutput())
    result = run_weekly_review(sample_topic, db, client, _make_settings(), dry_run=True)
    assert result is None
    client.chat.completions.create.assert_not_called()


# ---------------------------------------------------------------------------
# run_weekly_review calls model and returns parsed WeeklyReviewOutput
# ---------------------------------------------------------------------------


def test_run_weekly_review_returns_parsed_output(db, sample_topic, capsys):
    canned = WeeklyReviewOutput(
        dossier_rewrite="Updated dossier text.",
        promoted_observation_ids=[],
        notes=["Week was uneventful."],
    )
    client = _make_weekly_client(canned)
    result = run_weekly_review(sample_topic, db, client, _make_settings(), dry_run=False)

    assert result is not None
    assert isinstance(result, WeeklyReviewOutput)
    assert result.dossier_rewrite == "Updated dossier text."
    assert result.notes == ["Week was uneventful."]
    client.chat.completions.create.assert_called_once()


def test_run_weekly_review_caches_system_prompt(db, sample_topic):
    """Weekly system prompt must carry a cache_control breakpoint, like the daily path."""
    client = _make_weekly_client(WeeklyReviewOutput())
    run_weekly_review(sample_topic, db, client, _make_settings(), dry_run=False)

    api_messages = client.chat.completions.create.call_args.kwargs["messages"]
    sys_msg = next(m for m in api_messages if m["role"] == "system")
    assert isinstance(sys_msg["content"], list)
    assert sys_msg["content"][0]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# apply_weekly_review — dossier rewrite and observation promotion
# ---------------------------------------------------------------------------


def test_apply_weekly_review_rewrites_dossier(db, sample_topic):
    output = WeeklyReviewOutput(
        dossier_rewrite="New dossier content.",
        promoted_observation_ids=[],
    )
    apply_weekly_review(sample_topic.id, output, db)
    assert get_dossier(sample_topic.id, db) == "New dossier content."


def test_apply_weekly_review_none_dossier_leaves_unchanged(db, sample_topic):
    # Set an initial dossier via a prior review
    initial = WeeklyReviewOutput(dossier_rewrite="Original.", promoted_observation_ids=[])
    apply_weekly_review(sample_topic.id, initial, db)

    output = WeeklyReviewOutput(dossier_rewrite=None, promoted_observation_ids=[])
    apply_weekly_review(sample_topic.id, output, db)
    assert get_dossier(sample_topic.id, db) == "Original."


def test_apply_weekly_review_promotes_listed_observations(db, sample_topic):
    obs_id_1 = _insert_obs(sample_topic.id, db, "Durable signal A", importance=3)
    obs_id_2 = _insert_obs(sample_topic.id, db, "Transient signal B", importance=2)
    db.commit()

    output = WeeklyReviewOutput(
        dossier_rewrite=None,
        promoted_observation_ids=[obs_id_1],
    )
    apply_weekly_review(sample_topic.id, output, db)

    row1 = db.execute("SELECT status FROM observations WHERE id = ?", (obs_id_1,)).fetchone()
    row2 = db.execute("SELECT status FROM observations WHERE id = ?", (obs_id_2,)).fetchone()
    assert row1["status"] == "promoted"
    assert row2["status"] == "active"


def test_apply_weekly_review_promotes_scoped_to_topic(db, sample_topic):
    """An obs_id in another topic must not be promoted even if listed."""
    # Create a second topic
    cur = db.execute(
        "INSERT INTO topics (user_id, slug, name, brief)"
        " VALUES (1, 'other-topic', 'Other', 'Other')"
    )
    db.commit()
    other_topic_id = cur.lastrowid

    obs_other = _insert_obs(other_topic_id, db, "Other topic obs", importance=3)
    obs_mine = _insert_obs(sample_topic.id, db, "My topic obs", importance=3)
    db.commit()

    # Try to promote obs_other via sample_topic — must be a no-op for that row
    output = WeeklyReviewOutput(
        dossier_rewrite=None,
        promoted_observation_ids=[obs_other, obs_mine],
    )
    apply_weekly_review(sample_topic.id, output, db)

    row_other = db.execute("SELECT status FROM observations WHERE id = ?", (obs_other,)).fetchone()
    row_mine = db.execute("SELECT status FROM observations WHERE id = ?", (obs_mine,)).fetchone()
    assert row_other["status"] == "active", "obs in other topic must remain active"
    assert row_mine["status"] == "promoted"


def test_apply_weekly_review_is_transactional(db, sample_topic, monkeypatch):
    """If update_dossier raises, the observation promotion must also be rolled back."""
    obs_id = _insert_obs(sample_topic.id, db, "Some obs", importance=2)
    db.commit()

    import perpetual_analyst.analyst.compaction as compaction_mod

    def _boom(topic_id, content, conn):
        raise RuntimeError("simulated dossier failure")

    monkeypatch.setattr(compaction_mod, "update_dossier", _boom)

    output = WeeklyReviewOutput(
        dossier_rewrite="Should not persist.",
        promoted_observation_ids=[obs_id],
    )

    with pytest.raises(RuntimeError):
        apply_weekly_review(sample_topic.id, output, db)

    # Nothing must have committed — obs must still be active
    row = db.execute("SELECT status FROM observations WHERE id = ?", (obs_id,)).fetchone()
    assert row["status"] == "active", "observation must not have been promoted"
