"""Text extraction helpers: trafilatura for web pages, pypdf for PDFs."""

from __future__ import annotations

from typing import NamedTuple

import httpx
import trafilatura

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; PerpetualAnalyst/0.1; +https://github.com/perpetual-analyst)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_MIN_ARTICLE_CHARS = 200
_BOT_WALL_PHRASES = (
    "please enable js",
    "enable javascript",
    "disable any ad blocker",
    "checking your browser",
    "just a moment",
    "access denied",
    "captcha",
    "datadome",
    "cloudflare",
)
_BOT_WALL_MARKERS = (
    "captcha-delivery.com",
    "cf-browser-verification",
    "challenge-platform",
)


class ArticleFetchError(Exception):
    """Raised when a URL cannot be fetched or article text cannot be extracted."""


class FetchedArticle(NamedTuple):
    title: str | None
    text: str


def _looks_like_bot_wall(html: str, text: str | None, status_code: int) -> bool:
    lower_html = html.lower()
    lower_text = (text or "").lower()
    if status_code in {401, 403}:
        return True
    if any(marker in lower_html for marker in _BOT_WALL_MARKERS):
        return True
    if text and len(text) < _MIN_ARTICLE_CHARS:
        if any(phrase in lower_text for phrase in _BOT_WALL_PHRASES):
            return True
    return False


def extract_url(url: str, *, timeout: float = 30.0) -> FetchedArticle:
    """Fetch a URL and extract article text. Raises ArticleFetchError on failure."""
    try:
        response = httpx.get(
            url,
            headers=_DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise ArticleFetchError(f"Failed to fetch {url}: {exc}") from exc

    html = response.text
    text = trafilatura.extract(html, include_comments=False, include_tables=True)

    if _looks_like_bot_wall(html, text, response.status_code):
        raise ArticleFetchError(
            f"Could not extract article text from {url}: the site returned a "
            f"bot-protection page (HTTP {response.status_code}). "
            "Save the article to a file and use --file, or paste text via stdin."
        )

    if not text or len(text.strip()) < _MIN_ARTICLE_CHARS:
        raise ArticleFetchError(
            f"Could not extract article text from {url} "
            f"(HTTP {response.status_code}, extracted {len(text or '')} chars)."
        )

    title = None
    metadata = trafilatura.extract_metadata(html)
    if metadata and metadata.title:
        title = metadata.title

    return FetchedArticle(title=title, text=text)
