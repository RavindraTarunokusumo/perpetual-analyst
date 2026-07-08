# Session Archive: Firecrawl source extraction pipeline

**Merged:** PR #10 — merge commit `b982ab9` into `main`
**Branch:** `firecrawl-source-extraction`
**Worktree:** `.worktree/firecrawl-source-extraction`
**Date:** 2026-07-08
**Spec:** `docs/specs/2026-07-08-firecrawl-source-extraction.md`
**Plan:** `docs/specs/2026-07-08-firecrawl-source-extraction-plan.md`

---

## Outcome

Unified URL article extraction through `extract_url()` with trafilatura-first parsing and
Firecrawl `/scrape` fallback when bot walls or short content block local extraction. RSS
ingestion and `pa_inspect --url` share the same path. Item-level RSS failures fall back to
feed summary without incrementing `fetch_error_count`.

Live smoke validated Reuters bot-protected pages with real `FIRECRAWL_API_KEY` (~10k chars
extracted in ~1.7s).

## Landed sub-items

- [x] Spec + plan accepted — `2ff3de4`
- [x] Shared `extract_url` + bot-wall detection + `pa_inspect` wiring — `fcae3f1`
- [x] `get_or_create_watch_topic(name: str | None)` fix — `8578eb5`
- [x] `firecrawl-py` dep + `.env.example` + never-log invariant — `9849fae`
- [x] Firecrawl fallback in `extract_url` — `faa9cb7`
- [x] RSS → `extract_url` — `cfb35f3`
- [x] Live smoke test (`pytest -m smoke`) — `da2fa18`
- [x] Architecture doc update — `699a09f`
- [x] PR review fixes (RSS broad catch, sanitized Firecrawl errors, regression tests) — `77fa9f5`

## PR review (post-open `/review`)

- Posted PENDING GitHub review with 2 bugs, 4 suggestions, 1 nit.
- Fixed blocking bugs before merge: broad `except Exception` in `rss._extract_text`; full
  Firecrawl response parsing wrapped in `ArticleFetchError`; sanitized API error messages.

## Validation

- `pytest tests/test_extract.py tests/test_rss.py tests/test_ingestion.py` — 26 passed
- Live: `pytest -m smoke tests/test_extract_smoke.py` with `FIRECRAWL_API_KEY` — passed

## Notes

- Full `pytest` still has pre-existing collection errors on `main` (unrelated).
- GitNexus repo not indexed at session start; impact analysis skipped.