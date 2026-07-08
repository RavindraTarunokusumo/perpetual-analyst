from unittest.mock import MagicMock, patch

import pytest

from perpetual_analyst.ingestion.extract import ArticleFetchError, extract_url

_REUTERS_HTML = """<html><body>
<p id="cmsg">Please enable JS and disable any ad blocker</p>
<script src="https://ct.captcha-delivery.com/i.js"></script>
</body></html>"""

_ARTICLE_HTML = """<html><head><title>Sample Headline</title></head><body>
<article><p>{}</p></article></body></html>""".format("A" * 300)


def _mock_response(*, status_code: int, text: str) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


def test_extract_url_success():
    with patch(
        "perpetual_analyst.ingestion.extract.httpx.get",
        return_value=_mock_response(status_code=200, text=_ARTICLE_HTML),
    ):
        fetched = extract_url("https://example.com/article")

    assert len(fetched.text) >= 200
    assert fetched.title == "Sample Headline"


def test_extract_url_detects_bot_wall():
    with patch(
        "perpetual_analyst.ingestion.extract.httpx.get",
        return_value=_mock_response(status_code=401, text=_REUTERS_HTML),
    ):
        with pytest.raises(ArticleFetchError, match="bot-protection page"):
            extract_url("https://www.reuters.com/world/example")


def test_extract_url_rejects_short_content():
    short_html = "<html><body><p>Too short.</p></body></html>"
    with patch(
        "perpetual_analyst.ingestion.extract.httpx.get",
        return_value=_mock_response(status_code=200, text=short_html),
    ):
        with pytest.raises(ArticleFetchError, match="extracted"):
            extract_url("https://example.com/short")
