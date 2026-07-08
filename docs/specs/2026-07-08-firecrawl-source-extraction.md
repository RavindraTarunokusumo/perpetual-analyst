# Firecrawl Source Extraction Fallback — Design Spec

**Status:** Accepted (user approval 2026-07-08)
**Branch:** `firecrawl-source-extraction`
**Worktree:** `.worktree/firecrawl-source-extraction`
**Owner:** solo developer

## 1. Goal

Extract clean article text from URLs during RSS ingestion and CLI inspection. Use free
local trafilatura (httpx fetch) for most pages; escalate to Firecrawl `/scrape` only when
trafilatura hits bot-protection walls or returns unusably short content.

Unify all URL article extraction through a single `extract_url()` helper so daily RSS
ingestion and `pa_inspect --url` share the same fallback behavior.

## 2. Decisions (locked)

1. **Fallback only** — trafilatura first; Firecrawl on bot-wall or short-content failure.
2. **Full pipeline** — `rss.py` calls shared `extract_url()`; not CLI-only.
3. **Item-level RSS semantics preserved** — extraction failure on one feed entry falls back
   to the feed summary; does not increment `fetch_error_count`.
4. **Markdown output** — Firecrawl returns `markdown` with `only_main_content=True`.
5. **No API key → no Firecrawl** — if `FIRECRAWL_API_KEY` is unset, bot-wall failures
   raise `ArticleFetchError` (current behavior).

## 3. Architecture

```
URL
 └─▶ extract_url()  [ingestion/extract.py — single entry point]
      ├─ 1. httpx + trafilatura
      │     └─ success (≥200 chars, no bot wall) → FetchedArticle(title, text)
      ├─ 2. bot-wall or short-content?
      │     ├─ FIRECRAWL_API_KEY set → Firecrawl.scrape(markdown, only_main_content)
      │     └─ no key → ArticleFetchError
      └─▶ FetchedArticle(title, text)

rss._extract_text(url, summary)
 └─▶ extract_url(url) on success → text
 └─▶ ArticleFetchError → summary (item-level, not feed failure)

pa_inspect --url
 └─▶ extract_url(url) — already wired in WIP; propagates ArticleFetchError to stderr
```

## 4. File boundaries

| File | Change |
|---|---|
| `src/perpetual_analyst/ingestion/extract.py` | Add `_scrape_with_firecrawl()`; extend `extract_url()` fallback |
| `src/perpetual_analyst/ingestion/rss.py` | Replace inline trafilatura with `extract_url()` |
| `scripts/pa_inspect.py` | No further change (WIP already uses `extract_url`) |
| `pyproject.toml` | Add `firecrawl-py` dependency |
| `.env.example` | Add `FIRECRAWL_API_KEY=` |
| `AGENTS.md` / `CLAUDE.md` | Add `FIRECRAWL_API_KEY` to never-log invariant list |
| `tests/test_extract.py` | Firecrawl fallback + no-key paths |
| `tests/test_rss.py` | Mock `extract_url` instead of `trafilatura.fetch_url` |
| `tests/test_extract_smoke.py` | Optional live smoke test (`pytest -m smoke`) |

**Out of scope (separate commit):** `substrate.py` `get_or_create_watch_topic(name: str | None)` fix.

## 5. Firecrawl contract

```python
from firecrawl import Firecrawl

client = Firecrawl(api_key=os.environ["FIRECRAWL_API_KEY"])
doc = client.scrape(url, formats=["markdown"], only_main_content=True)
text = doc.markdown or ""
title = doc.metadata.title if doc.metadata else None
```

- Reuse `_MIN_ARTICLE_CHARS = 200` threshold on Firecrawl output.
- Read `FIRECRAWL_API_KEY` from env at call time; never log it.
- Firecrawl SDK errors → wrap in `ArticleFetchError` with a safe message (no key leakage).
- Lazy-import `firecrawl` inside `_scrape_with_firecrawl()` to avoid import cost on happy path.

## 6. Data model / migration impact

None. `items.raw_text` continues to store extracted clean text; `content_hash` dedupe unchanged.

## 7. Invariant impact

- **Inv #7 (secrets):** add `FIRECRAWL_API_KEY` to the never-log list in `AGENTS.md` and `CLAUDE.md`.
- **Inv #8 (content_hash):** unchanged.
- **One analyst call per topic per day:** unchanged — extraction is zero LLM calls.

## 8. Non-goals

- Firecrawl-first or per-source `extraction: firecrawl` config
- Firecrawl `/interact` for multi-step pages
- Inbox PDF extraction via Firecrawl
- `FIRECRAWL_API_URL` self-hosted support (defer)
- Changing RSS feed-level error counting semantics

## 9. Validation plan

1. **Unit tests (mocked):**
   - trafilatura success (existing 3 tests)
   - bot-wall → Firecrawl fallback returns text
   - bot-wall + no API key → `ArticleFetchError`
   - Firecrawl returns short markdown → `ArticleFetchError`
   - RSS `_extract_text` falls back to summary on `ArticleFetchError`
2. **Regression:** full `pytest` suite green (excluding smoke by default).
3. **Live smoke** (`pytest -m smoke`): one bot-protected URL with real `FIRECRAWL_API_KEY` in `.env`.

## 10. Risks

- **Cost:** Firecrawl credits consumed only on trafilatura failure; monitor scrape volume on
  bot-heavy feeds.
- **Latency:** Firecrawl adds seconds per failed article; acceptable for fallback path only.
- **Dependency:** new `firecrawl-py` package; pin minimum version in `pyproject.toml`.

## 11. Unresolved questions

None.

## 12. Success criteria

1. `extract_url()` succeeds on bot-protected pages when `FIRECRAWL_API_KEY` is set.
2. `rss.py` uses `extract_url()`; item-level failures still fall back to feed summary.
3. `pa_inspect --url` uses the same path.
4. All unit tests pass; live smoke test documents Reuters-style extraction when run explicitly.