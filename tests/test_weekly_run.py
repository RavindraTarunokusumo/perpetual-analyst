"""Tests for the weekly compaction orchestrator (weekly_run.main). See SPEC §8."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

from perpetual_analyst.analyst.memory import insert_observation
from perpetual_analyst.analyst.schemas import NewObservation, WeeklyReviewOutput
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
    obs = NewObservation(kind="signal", content=content, importance=importance, source_item_ids=[])
    return insert_observation(topic_id, obs, conn)


# ---------------------------------------------------------------------------
# dry_run — no API call
# ---------------------------------------------------------------------------


def test_dry_run_does_not_call_client(db, sample_topic, monkeypatch):
    mock_client = _make_weekly_client(WeeklyReviewOutput())

    monkeypatch.setattr("perpetual_analyst.weekly_run.init_db", lambda *_a, **_k: db)
    monkeypatch.setattr("perpetual_analyst.weekly_run.make_client", lambda: mock_client)
    monkeypatch.setattr("perpetual_analyst.weekly_run.load_settings", _make_settings)

    from perpetual_analyst.weekly_run import main

    main(dry_run=True)

    mock_client.chat.completions.create.assert_not_called()


# ---------------------------------------------------------------------------
# live run — client called once, apply path executes
# ---------------------------------------------------------------------------


def test_live_run_calls_client_and_applies(db, sample_topic, monkeypatch):
    obs_id = _insert_obs(sample_topic.id, db, "Durable signal", importance=3)
    db.commit()

    canned = WeeklyReviewOutput(
        dossier_rewrite="New dossier.",
        promoted_observation_ids=[obs_id],
    )
    mock_client = _make_weekly_client(canned)

    monkeypatch.setattr("perpetual_analyst.weekly_run.init_db", lambda *_a, **_k: db)
    monkeypatch.setattr("perpetual_analyst.weekly_run.make_client", lambda: mock_client)
    monkeypatch.setattr("perpetual_analyst.weekly_run.load_settings", _make_settings)

    from perpetual_analyst.weekly_run import main

    main(dry_run=False)

    mock_client.chat.completions.create.assert_called_once()

    row = db.execute("SELECT status FROM observations WHERE id = ?", (obs_id,)).fetchone()
    assert row["status"] == "promoted"


# ---------------------------------------------------------------------------
# per-topic error isolation
# ---------------------------------------------------------------------------


def test_error_in_run_weekly_review_does_not_propagate(db, sample_topic, monkeypatch):
    monkeypatch.setattr("perpetual_analyst.weekly_run.init_db", lambda *_a, **_k: db)
    monkeypatch.setattr("perpetual_analyst.weekly_run.make_client", lambda: MagicMock())
    monkeypatch.setattr("perpetual_analyst.weekly_run.load_settings", _make_settings)

    import perpetual_analyst.weekly_run as weekly_mod

    def _boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(weekly_mod, "run_weekly_review", _boom)

    # Must not raise
    weekly_mod.main(dry_run=False)


# ---------------------------------------------------------------------------
# no active topics → early return, no client instantiated
# ---------------------------------------------------------------------------


def test_no_active_topics_returns_early(db, monkeypatch, capsys):
    # No topics inserted — DB is empty; dry_run=True so make_client is never called
    monkeypatch.setattr("perpetual_analyst.weekly_run.init_db", lambda *_a, **_k: db)
    monkeypatch.setattr("perpetual_analyst.weekly_run.load_settings", _make_settings)

    from perpetual_analyst.weekly_run import main

    main(dry_run=True)

    captured = capsys.readouterr()
    assert "nothing to do" in captured.out
