from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from perpetual_analyst import daily_run


@pytest.fixture
def two_topics(db):
    db.execute("INSERT INTO topics (user_id, slug, name, active) VALUES (1, 'a', 'A', 1)")
    db.execute("INSERT INTO topics (user_id, slug, name, active) VALUES (1, 'b', 'B', 1)")
    db.execute("INSERT INTO topics (user_id, slug, name, active) VALUES (1, 'off', 'Off', 0)")
    db.commit()
    return db


@pytest.fixture
def quiet_stages(monkeypatch):
    """Neutralize all pipeline stages; tests re-patch what they assert on."""
    monkeypatch.setattr(daily_run, "load_topics", lambda: [])
    monkeypatch.setattr(daily_run, "load_sources", lambda: [])
    monkeypatch.setattr(daily_run, "sync_config", MagicMock())
    monkeypatch.setattr(daily_run, "fetch_rss", MagicMock(return_value=0))
    monkeypatch.setattr(daily_run, "scan_inbox", MagicMock(return_value=[]))
    monkeypatch.setattr(daily_run, "triage_items", MagicMock(return_value=[]))
    monkeypatch.setattr(daily_run, "select_analyst_items", MagicMock(return_value=[]))
    monkeypatch.setattr(daily_run, "run_topic", MagicMock(return_value=None))
    monkeypatch.setattr(daily_run, "assemble_report", MagicMock(return_value=("digest", "full")))
    monkeypatch.setattr(daily_run, "persist_report", MagicMock(return_value=1))
    monkeypatch.setattr(daily_run, "retry_undelivered", MagicMock(return_value=0))
    return monkeypatch


def test_failing_topic_does_not_kill_run(two_topics, quiet_stages, settings):
    analysis = MagicMock()
    calls = []

    def _run_topic(topic, items, conn, client, s, dry_run=False):
        calls.append(topic.slug)
        if topic.slug == "a":
            raise RuntimeError("boom")
        return analysis

    quiet_stages.setattr(daily_run, "run_topic", _run_topic)
    daily_run.run_daily(two_topics, MagicMock(), settings)
    assert calls == ["a", "b"]
    assert daily_run.assemble_report.call_count == 1
    results = daily_run.assemble_report.call_args.args[0]
    assert [t.slug for t, _ in results] == ["b"]


def test_per_day_guard_skips_analysis_but_retries_delivery(two_topics, quiet_stages, settings):
    two_topics.execute("INSERT INTO reports (report_date, digest_text) VALUES (date('now'), 'd')")
    two_topics.commit()
    daily_run.run_daily(two_topics, MagicMock(), settings)
    assert daily_run.run_topic.call_count == 0
    assert daily_run.assemble_report.call_count == 0
    assert daily_run.retry_undelivered.call_count == 1


def test_topic_filter(two_topics, quiet_stages, settings):
    quiet_stages.setattr(daily_run, "run_topic", MagicMock(return_value=MagicMock()))
    daily_run.run_daily(two_topics, MagicMock(), settings, topic_slug="b")
    assert daily_run.run_topic.call_count == 1
    topic_arg = daily_run.run_topic.call_args.args[0]
    assert topic_arg.slug == "b"


def test_dry_run_skips_triage_assembly_and_delivery(two_topics, quiet_stages, settings):
    quiet_stages.setattr(daily_run, "select_analyst_items", MagicMock(return_value=[MagicMock()]))
    daily_run.run_daily(two_topics, None, settings, dry_run=True)
    assert daily_run.triage_items.call_count == 0
    assert daily_run.assemble_report.call_count == 0
    assert daily_run.persist_report.call_count == 0
    assert daily_run.retry_undelivered.call_count == 0
    assert daily_run.run_topic.call_count == 2  # dry prompts still printed


def test_no_results_skips_assembly(two_topics, quiet_stages, settings):
    daily_run.run_daily(two_topics, MagicMock(), settings)
    assert daily_run.assemble_report.call_count == 0
    assert daily_run.retry_undelivered.call_count == 1
