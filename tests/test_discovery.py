"""Tests for weekly source-discovery run. See SPEC §11."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

from perpetual_analyst.analyst.schemas import DiscoveryCandidate, DiscoveryOutput
from perpetual_analyst.config import ModelConfig, Settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(thinking: bool = False) -> Settings:
    return Settings(
        analyst=ModelConfig(id="anthropic/claude-3-haiku", thinking=thinking),
        triage=ModelConfig(id="anthropic/claude-3-haiku", thinking=False),
    )


def _make_discovery_client(output: DiscoveryOutput) -> MagicMock:
    """Build a mock OpenAI client whose create() returns the given DiscoveryOutput as JSON."""
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


# ---------------------------------------------------------------------------
# _domain helper
# ---------------------------------------------------------------------------


def test_domain_strips_www():
    from perpetual_analyst.analyst.discovery import _domain

    assert _domain("https://www.example.com/x") == "example.com"


def test_domain_no_www():
    from perpetual_analyst.analyst.discovery import _domain

    assert _domain("https://feeds.reuters.com/reuters/topNews") == "feeds.reuters.com"


def test_domain_none_returns_none():
    from perpetual_analyst.analyst.discovery import _domain

    assert _domain(None) is None


def test_domain_empty_returns_none():
    from perpetual_analyst.analyst.discovery import _domain

    assert _domain("") is None


# ---------------------------------------------------------------------------
# mine_outbound_domains
# ---------------------------------------------------------------------------


def _seed_discovery_db(db: sqlite3.Connection, topic_id: int) -> int:
    """Seed one source linked to the topic, with items on two domains, and citations."""
    source_id = db.execute("INSERT INTO sources (type, name) VALUES ('rss', 'Feed A')").lastrowid
    db.execute(
        "INSERT INTO topic_sources (topic_id, source_id) VALUES (?, ?)",
        (topic_id, source_id),
    )
    # 3 items on domain-a, 1 item on domain-b, 1 item with NULL url
    item_ids = []
    for url, chash in [
        ("https://domain-a.com/story1", "h1"),
        ("https://domain-a.com/story2", "h2"),
        ("https://domain-a.com/story3", "h3"),
        ("https://www.domain-b.com/article", "h4"),
        (None, "h5"),
    ]:
        iid = db.execute(
            "INSERT INTO items (source_id, url, content_hash) VALUES (?, ?, ?)",
            (source_id, url, chash),
        ).lastrowid
        item_ids.append(iid)

    # Cite items 0,1,2 (domain-a × 3) and item 3 (domain-b × 1); skip item 4 (NULL url)
    for iid in item_ids[:4]:
        db.execute(
            "INSERT INTO citations (item_id, source_id) VALUES (?, ?)",
            (iid, source_id),
        )
    db.commit()
    return source_id


def test_mine_outbound_domains_ranked_by_count(db, sample_topic):
    from perpetual_analyst.analyst.discovery import mine_outbound_domains

    _seed_discovery_db(db, sample_topic.id)
    results = mine_outbound_domains(sample_topic.id, db)

    assert len(results) >= 2
    domains = [d for d, _ in results]
    # domain-a cited 3×, domain-b cited 1×
    assert domains[0] == "domain-a.com"
    assert domains[1] == "domain-b.com"
    counts = [c for _, c in results]
    assert counts[0] == 3
    assert counts[1] == 1


def test_mine_outbound_domains_skips_null_url(db, sample_topic):
    from perpetual_analyst.analyst.discovery import mine_outbound_domains

    _seed_discovery_db(db, sample_topic.id)
    results = mine_outbound_domains(sample_topic.id, db)
    # NULL-url item should not contribute any domain
    domains = [d for d, _ in results]
    assert None not in domains
    assert "" not in domains


def test_mine_outbound_domains_empty_when_no_sources(db, sample_topic):
    from perpetual_analyst.analyst.discovery import mine_outbound_domains

    results = mine_outbound_domains(sample_topic.id, db)
    assert results == []


def test_mine_outbound_domains_respects_limit(db, sample_topic):
    from perpetual_analyst.analyst.discovery import mine_outbound_domains

    _seed_discovery_db(db, sample_topic.id)
    results = mine_outbound_domains(sample_topic.id, db, limit=1)
    assert len(results) == 1


# ---------------------------------------------------------------------------
# web_search_extra — provider seam contract
# ---------------------------------------------------------------------------


def test_extract_json_object_strips_prose():
    """Web-search responses prepend prose before the JSON; extraction must recover the object."""
    from perpetual_analyst.analyst.discovery import _extract_json_object

    raw = 'I\'ll research current sources. {"candidates": [{"url": "https://x.com"}]}'
    assert _extract_json_object(raw) == '{"candidates": [{"url": "https://x.com"}]}'


def test_extract_json_object_strips_code_fence():
    from perpetual_analyst.analyst.discovery import _extract_json_object

    raw = '```json\n{"candidates": []}\n```'
    assert _extract_json_object(raw) == '{"candidates": []}'


def test_discover_sources_parses_prose_wrapped_response(db, sample_topic):
    """A live web-search reply with leading prose must still parse into DiscoveryOutput."""
    from perpetual_analyst.analyst.discovery import discover_sources

    client = _make_discovery_client(DiscoveryOutput())
    # Override the mock content to mimic the real web-search reply shape (prose + JSON).
    client.chat.completions.create.return_value.choices[0].message.content = (
        'Here are some sources I found. {"candidates": '
        '[{"url": "https://feeds.x.org/rss", "domain": "x.org", "rationale": "Fills gap Y."}]}'
    )
    result = discover_sources(sample_topic, db, client, _make_settings())
    assert result is not None
    assert len(result.candidates) == 1
    assert result.candidates[0].domain == "x.org"


def test_web_search_extra_contains_plugins():
    from perpetual_analyst.analyst.discovery import web_search_extra

    extra = web_search_extra()
    assert "plugins" in extra
    assert isinstance(extra["plugins"], list)
    assert len(extra["plugins"]) >= 1
    assert extra["plugins"][0]["id"] == "web"


def test_web_search_extra_perplexity_has_no_openrouter_plugins():
    from perpetual_analyst.analyst.discovery import web_search_extra

    assert web_search_extra("perplexity") == {}


# ---------------------------------------------------------------------------
# discover_sources — dry_run
# ---------------------------------------------------------------------------


def test_discover_sources_dry_run_returns_none_no_api_call(db, sample_topic, capsys):
    from perpetual_analyst.analyst.discovery import discover_sources

    client = _make_discovery_client(DiscoveryOutput())
    result = discover_sources(sample_topic, db, client, _make_settings(), dry_run=True)
    assert result is None
    client.chat.completions.create.assert_not_called()


# ---------------------------------------------------------------------------
# discover_sources — live (mock client)
# ---------------------------------------------------------------------------


def test_discover_sources_returns_parsed_output(db, sample_topic):
    from perpetual_analyst.analyst.discovery import discover_sources

    canned = DiscoveryOutput(
        candidates=[
            DiscoveryCandidate(
                url="https://feeds.example.com/rss",
                domain="example.com",
                rationale="Covers the gap in X.",
            )
        ]
    )
    client = _make_discovery_client(canned)
    result = discover_sources(sample_topic, db, client, _make_settings())

    assert result is not None
    assert isinstance(result, DiscoveryOutput)
    assert len(result.candidates) == 1
    assert result.candidates[0].url == "https://feeds.example.com/rss"


def test_discover_sources_inserts_into_source_candidates(db, sample_topic):
    from perpetual_analyst.analyst.discovery import discover_sources

    canned = DiscoveryOutput(
        candidates=[
            DiscoveryCandidate(
                url="https://feeds.example.com/rss",
                domain="example.com",
                rationale="Gap filler.",
            )
        ]
    )
    client = _make_discovery_client(canned)
    discover_sources(sample_topic, db, client, _make_settings())

    rows = db.execute(
        "SELECT topic_id, url, domain, status FROM source_candidates WHERE topic_id = ?",
        (sample_topic.id,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["topic_id"] == sample_topic.id
    assert rows[0]["url"] == "https://feeds.example.com/rss"
    assert rows[0]["status"] == "pending"


def test_discover_sources_no_duplicate_on_rerun(db, sample_topic):
    from perpetual_analyst.analyst.discovery import discover_sources

    canned = DiscoveryOutput(
        candidates=[
            DiscoveryCandidate(
                url="https://feeds.example.com/rss",
                domain="example.com",
                rationale="Gap filler.",
            )
        ]
    )
    client = _make_discovery_client(canned)
    discover_sources(sample_topic, db, client, _make_settings())
    discover_sources(sample_topic, db, client, _make_settings())

    rows = db.execute(
        "SELECT COUNT(*) as cnt FROM source_candidates WHERE topic_id = ?",
        (sample_topic.id,),
    ).fetchone()
    assert rows["cnt"] == 1


def test_discover_sources_extra_body_contains_plugins(db, sample_topic):
    from perpetual_analyst.analyst.discovery import discover_sources

    canned = DiscoveryOutput()
    client = _make_discovery_client(canned)
    discover_sources(sample_topic, db, client, _make_settings())

    kwargs = client.chat.completions.create.call_args.kwargs
    extra_body = kwargs["extra_body"]
    assert "plugins" in extra_body


def test_discover_sources_thinking_flag_adds_thinking_key(db, sample_topic):
    from perpetual_analyst.analyst.discovery import discover_sources

    canned = DiscoveryOutput()
    client = _make_discovery_client(canned)
    discover_sources(sample_topic, db, client, _make_settings(thinking=True))

    kwargs = client.chat.completions.create.call_args.kwargs
    extra_body = kwargs["extra_body"]
    assert "thinking" in extra_body
    assert extra_body["thinking"] == {"type": "adaptive"}


def test_discover_sources_perplexity_uses_discovery_model_without_plugins(db, sample_topic):
    from perpetual_analyst.analyst.discovery import discover_sources
    from perpetual_analyst.config import DiscoveryConfig

    canned = DiscoveryOutput()
    client = _make_discovery_client(canned)
    settings = _make_settings()
    settings.discovery = DiscoveryConfig(provider="perplexity", model="sonar")

    discover_sources(sample_topic, db, client, settings)

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "sonar"
    assert kwargs["extra_body"] == {}


def test_discover_sources_derives_domain_when_empty(db, sample_topic):
    """If DiscoveryCandidate.domain is empty, discover_sources derives it from the URL."""
    from perpetual_analyst.analyst.discovery import discover_sources

    canned = DiscoveryOutput(
        candidates=[
            DiscoveryCandidate(
                url="https://www.nodomain-set.com/feed",
                domain="",
                rationale="Missing domain field.",
            )
        ]
    )
    client = _make_discovery_client(canned)
    discover_sources(sample_topic, db, client, _make_settings())

    row = db.execute(
        "SELECT domain FROM source_candidates WHERE topic_id = ?",
        (sample_topic.id,),
    ).fetchone()
    assert row["domain"] == "nodomain-set.com"
