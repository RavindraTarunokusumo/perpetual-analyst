"""Text extraction helpers: trafilatura for web pages, Firecrawl fallback, pypdf for PDFs."""

from __future__ import annotations

import os
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


def _extract_with_trafilatura(html: str, status_code: int) -> FetchedArticle | None:
    text = trafilatura.extract(html, include_comments=False, include_tables=True)
    if _looks_like_bot_wall(html, text, status_code):
        return None
    if not text or len(text.strip()) < _MIN_ARTICLE_CHARS:
        return None

    title = None
    metadata = trafilatura.extract_metadata(html)
    if metadata and metadata.title:
        title = metadata.title
    return FetchedArticle(title=title, text=text)


def _scrape_with_firecrawl(url: str, *, timeout: float) -> FetchedArticle:
    api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        raise ArticleFetchError(
            f"Could not extract article text from {url}: trafilatura failed and "
            "FIRECRAWL_API_KEY is not set. Save the article to a file and use --file, "
            "or paste text via stdin."
        )

    from firecrawl import Firecrawl

    client = Firecrawl(api_key=api_key)
    try:
        doc = client.scrape(
            url,
            formats=["markdown"],
            only_main_content=True,
            timeout=int(timeout * 1000),
        )
        markdown = (doc.markdown or "").strip()
        if len(markdown) < _MIN_ARTICLE_CHARS:
            raise ArticleFetchError(
                f"Could not extract article text from {url} "
                f"(Firecrawl returned {len(markdown)} chars)."
            )
        title = doc.metadata.title if doc.metadata and doc.metadata.title else None
    except ArticleFetchError:
        raise
    except Exception as exc:
        raise ArticleFetchError(f"Firecrawl scrape failed for {url}") from exc

    return FetchedArticle(title=title, text=markdown)


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

    try:
        html = response.text
        article = _extract_with_trafilatura(html, response.status_code)
        if article is not None:
            return article
        return _scrape_with_firecrawl(url, timeout=timeout)
    except ArticleFetchError:
        raise
    except Exception as exc:
        raise ArticleFetchError(f"Could not extract article text from {url}") from exc