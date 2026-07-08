"""Live smoke tests for URL extraction with Firecrawl fallback.

Run explicitly:
    pytest -m smoke tests/test_extract_smoke.py -v

Requires FIRECRAWL_API_KEY in .env and network access.
"""

from __future__ import annotations

import os

import pytest

from perpetual_analyst.ingestion.extract import extract_url

pytestmark = pytest.mark.smoke


@pytest.fixture
def firecrawl_api_key() -> str:
    key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not key:
        pytest.skip("FIRECRAWL_API_KEY not set")
    return key


def test_extract_url_reuters_via_firecrawl_fallback(firecrawl_api_key: str) -> None:
    """Bot-protected Reuters pages should extract via Firecrawl when key is set."""
    _ = firecrawl_api_key
    fetched = extract_url("https://www.reuters.com/world/")
    assert len(fetched.text) >= 200