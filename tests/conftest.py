"""Shared fixtures for the test suite."""

# TODO (Task 1/2): Implement fixtures as modules are built.
#
# Key fixtures to add:
#
# @pytest.fixture
# def db():
#     """Fresh in-memory SQLite DB with full schema + FTS5 tables."""
#     from perpetual_analyst.store.db import init_db
#     conn = init_db(":memory:")
#     yield conn
#     conn.close()
#
# @pytest.fixture
# def mock_anthropic(monkeypatch):
#     """Stub client.messages.parse() to return a canned TopicAnalysis."""
#     ...
#
# @pytest.fixture
# def sample_topic(db):
#     """Insert a sample topic and return its ID."""
#     ...
