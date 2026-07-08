# Session Archive: PA ↔ Nexus integration

**Merged:** PA PR #9 — merge commit `a2c3876` into `phase-1-analyst-prototype`
**Upstream:** Nexus PR #33 — merge commit `d1c4eae` into Nexus `main` (pinned as PA submodule)
**Branch:** `pa-nexus-integration` (PA) · `pa-corpus-scope` (Nexus)
**Date:** 2026-07-08
**Spec:** `docs/specs/2026-07-08-pa-nexus-integration.md`
**Plan:** `docs/specs/2026-07-08-pa-nexus-integration-plan.md`

---

## Outcome

Integrated the benchmark-validated **Nexus** memory substrate (Postgres + pgvector
sentence-window retrieval, all-Qwen) into Perpetual Analyst, replacing the pre-Nexus
SQLite/FTS5 + `TopicAnalysis` daily path with a single **narrative-update synthesis loop**
per topic per day. `substrate.py` is the sole PA↔Nexus/Postgres boundary. Two-DB topology:
SQLite (operational) + Postgres (memory corpus + 8 analytical tables). Local
Qwen3-Embedding-0.6B @384-dim for ingest; `qwen3.7-max` synthesis; new `analyst ask` /
`analyst score` CLI; `./try.sh` inspection harness. Nexus wired as a git submodule.

Validated by live end-to-end runs against real Qwen + Postgres (not just unit tests):
cross-session narrative v1→v2 with `prev_version_id`, day-2 evidence superseding a day-1
claim, hypotheses retired within the ≤7 cap, scoped retrieval isolation, 384-dim spans.

## Landed sub-items (branch commits, pre-merge)

- A1 Qwen provider defaults + DashScope key — `b39a2b1`
- N1 corpus/topic-scoped retrieval (Nexus) — `cd4be18`
- D1 NarrativeUpdate + analytical schemas — `429d88b`
- A2 substrate ingest+retrieve boundary — `16b1a06`
- B1 analytical tables migration 0009 (Nexus) — `8a776a4`
- B2 get_or_create_watch_topic — `1aa126f`
- C daily ingest → corpus — `b16e209` (+ loop fix `78b7be6`)
- 0010 claims.document_id nullable (Nexus) — `37e87b2`/`27ab8ff`
- D2a substrate.synthesize — `95cf947`
- D2b substrate.persist_bundle (transactional) — `6414959`
- D3 synthesis orchestration — `a22336c`
- D4 daily_run narrative loop — (verified e2e)
- E1/E2 cross-session ask + score — (+ Nexus answer-scope `2ac181b`)
- F1/F2 retire FTS5/Voyage + TopicAnalysis — `544c1fb`
- G pin embedder Qwen3-Embedding-0.6B @384 — `86a11ca`
- Pre-PR: docs reconciled `2e011ad`; dead helper removed `5aaaa81`; submodule wired `41a20da`, bumped `6afd702`

## PR-review fixes (Grok, verified + addressed before merge)

- quality: score on hit_rate only; citations-derived weights retired (reserved for a
  third-party source-rating API) — `a923446`
- substrate: drop synth schema-retry (invariant #1); retire all non-`retired` hypotheses +
  fixed `status='active'`; compensating-delete on span-ingest failure; `[P#]` claim-index
  disambiguation — `2813c9d`
- daily: one `asyncio.run` per topic (fold ingest into `run_daily_for_topic`) — `5a7b9a5`
- tooling: `./try.sh` inspection harness — `5b04843`

## Deferred (carried to Future Backlog)

- Cross-topic `content_hash` dedupe gives a document one scope; a shared source item is
  invisible to later topics (needs a scope join-table / per-topic doc rows — schema change).
- Third-party source-rating API to replace the retired citation/uniqueness/freshness signals.
