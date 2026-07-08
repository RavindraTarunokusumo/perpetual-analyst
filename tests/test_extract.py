from unittest.mock import MagicMock, patch

import pytest

from perpetual_analyst.ingestion.extract import (
    ArticleFetchError,
    FetchedArticle,
    _scrape_with_firecrawl,
    extract_url,
)

_REUTERS_HTML = """<html><body>
<p id="cmsg">Please enable JS and disable any ad blocker</p>
<script src="https://ct.captcha-delivery.com/i.js"></script>
</body></html>"""

_ARTICLE_HTML = """<html><head><title>Sample Headline</title></head><body>
<article><p>{}</p></article></body></html>""".format("A" * 300)

_FIRECRAWL_TEXT = "B" * 300


def _mock_response(*, status_code: int, text: str) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


def test_extract_url_success():
    with (
        patch(
            "perpetual_analyst.ingestion.extract.httpx.get",
            return_value=_mock_response(status_code=200, text=_ARTICLE_HTML),
        ),
        patch("perpetual_analyst.ingestion.extract._scrape_with_firecrawl") as scrape,
    ):
        fetched = extract_url("https://example.com/article")

    scrape.assert_not_called()
    assert len(fetched.text) >= 200
    assert fetched.title == "Sample Headline"


def test_extract_url_bot_wall_without_firecrawl_key(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    with patch(
        "perpetual_analyst.ingestion.extract.httpx.get",
        return_value=_mock_response(status_code=401, text=_REUTERS_HTML),
    ):
        with pytest.raises(ArticleFetchError, match="FIRECRAWL_API_KEY is not set"):
            extract_url("https://www.reuters.com/world/example")


def test_extract_url_short_content_without_firecrawl_key(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    short_html = "<html><body><p>Too short.</p></body></html>"
    with patch(
        "perpetual_analyst.ingestion.extract.httpx.get",
        return_value=_mock_response(status_code=200, text=short_html),
    ):
        with pytest.raises(ArticleFetchError, match="FIRECRAWL_API_KEY is not set"):
            extract_url("https://example.com/short")


def test_extract_url_falls_back_to_firecrawl_on_bot_wall(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-key")
    fallback = FetchedArticle(title="Reuters Headline", text=_FIRECRAWL_TEXT)
    with (
        patch(
            "perpetual_analyst.ingestion.extract.httpx.get",
            return_value=_mock_response(status_code=401, text=_REUTERS_HTML),
        ),
        patch(
            "perpetual_analyst.ingestion.extract._scrape_with_firecrawl",
            return_value=fallback,
        ) as scrape,
    ):
        fetched = extract_url("https://www.reuters.com/world/example")

    scrape.assert_called_once()
    assert fetched.title == "Reuters Headline"
    assert len(fetched.text) >= 200


def test_extract_url_firecrawl_short_content_raises(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-key")
    with (
        patch(
            "perpetual_analyst.ingestion.extract.httpx.get",
            return_value=_mock_response(status_code=401, text=_REUTERS_HTML),
        ),
        patch(
            "perpetual_analyst.ingestion.extract._scrape_with_firecrawl",
            side_effect=ArticleFetchError("Firecrawl returned 12 chars."),
        ),
    ):
        with pytest.raises(ArticleFetchError, match="Firecrawl returned"):
            extract_url("https://www.reuters.com/world/example")


def test_scrape_with_firecrawl_uses_markdown_contract(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-key")
    doc = MagicMock()
    doc.markdown = "C" * 250
    doc.metadata = MagicMock(title="Firecrawl Title")
    client = MagicMock()
    client.scrape.return_value = doc
    with patch("firecrawl.Firecrawl", return_value=client):
        fetched = _scrape_with_firecrawl("https://example.com/article", timeout=30.0)

    client.scrape.assert_called_once_with(
        "https://example.com/article",
        formats=["markdown"],
        only_main_content=True,
        timeout=30000,
    )
    assert fetched.title == "Firecrawl Title"
    assert len(fetched.text) >= 200


def test_scrape_with_firecrawl_malformed_response_raises(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-key")
    client = MagicMock()
    client.scrape.return_value = None
    with patch("firecrawl.Firecrawl", return_value=client):
        with pytest.raises(ArticleFetchError, match="Firecrawl scrape failed"):
            _scrape_with_firecrawl("https://example.com/article", timeout=30.0)


def test_scrape_with_firecrawl_api_error_message_is_sanitized(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-secret-key")
    client = MagicMock()
    client.scrape.side_effect = RuntimeError("Bearer fc-secret-key invalid")
    with patch("firecrawl.Firecrawl", return_value=client):
        with pytest.raises(ArticleFetchError, match="Firecrawl scrape failed") as exc_info:
            _scrape_with_firecrawl("https://example.com/article", timeout=30.0)

    assert "fc-secret-key" not in str(exc_info.value)