# Harness Alignment And Backlog Spec

**Status:** Accepted by user request on 2026-07-08
**Branch:** `codex-align-harness-and-backlog`
**Owner:** Codex senior developer

## Goal

Align the repository instructions and agent harness to the canonical 7-step
Grok-junior workflow, then clear the four active backlog items while preserving
the project's eight core invariants, GitNexus MCP requirements, and the
one-analyst-call rule.

## Scope

1. Replace the current 9-step feature workflow in `AGENTS.md` and `CLAUDE.md`
   with the canonical 7-step workflow from
   `/root/.hermes/profiles/coder/documents/canonical_project_instruction_file.md`.
2. Mirror the workflow into `docs/agent-harness.md`, `SPEC.md`, and harness
   files so future agents use accepted specs in `docs/specs/`, Grok
   non-interactive handoffs, JSON output, senior-dev review, pre-commit, git
   notes, Pre-PR checks, PR review, archive, and workflow-only reflection.
3. Implement the Web UI approval flow and source/quality dashboard first.
4. Add uniqueness and freshness-lead metrics to `sources.quality_score`.
5. Add a configurable discovery-provider seam for OpenRouter web search and
   optional Perplexity discovery.
6. Add a gated sqlite-vec + Voyage embeddings upgrade path that remains off
   unless FTS insufficiency is explicitly recorded and embeddings are enabled.
7. Update `TODO.md` and `session_ledger.json`, then archive completed work only
   after commits/PR/merge steps are complete.

## Non-Goals

- No multi-agent analyst runtime, critic loops, debate crews, or extra daily
  analyst model calls.
- No automatic source removal.
- No automatic source approval without an explicit operator action in the local
  UI.
- No embeddings by default.
- No destructive git operations.

## Architecture

### Harness

`AGENTS.md` and `CLAUDE.md` become mirrored repo contracts. They keep the eight
core invariants verbatim and make GitNexus impact analysis mandatory before
symbol edits, with `gitnexus_detect_changes()` before commit. The implementation
workflow is spec-first:

- Step 1 identifies a branch/worktree, environment, status, and accepted spec.
- Step 2 queries the repo map/code graph.
- Step 3 plans from the accepted spec.
- Step 4 logs TODO items and delegates bounded implementation tasks to Grok
  junior sessions using `grok -p ... --output-format json`.
- Step 5 validates, stages specific files, commits each meaningful sub-item,
  and attaches git notes.
- Step 6 runs Pre-PR simplification, docs, test-plan, security review when
  applicable, and full validation.
- Step 7 submits a PR and processes Copilot/Grok review findings.

Post-PR archiving and reflection remain required session wrap-up actions, but
they are not numbered workflow steps.

### Web UI Approval Flow

Add a local, dependency-light operator UI served by the Python standard library:

- `analyst web --host 127.0.0.1 --port 8765`
- Dashboard: pending source candidates, existing source quality metrics,
  probation status, and bottom-decile candidates.
- Approval: POST action from candidate row with source type `rss` or `web`.
- Dismissal: POST action that marks a candidate rejected with an optional note.

Approval must validate URLs before any fetch:

- only `http` and `https`
- hostname required
- no credentials in URL
- block localhost, loopback, link-local, private, multicast, reserved, and
  unspecified IP targets
- resolve hostnames before fetch and reject private resolved addresses
- validate every redirect target before following it
- use timeouts and do not log secrets

Approved candidates create a new source in probation and link it to the
candidate topic. The candidate status becomes `approved`. Duplicate source URLs
for the same topic should not create duplicate links.

### Quality Metrics

Extend source quality from two factors to four:

- triage hit-rate
- citation rate
- uniqueness rate
- freshness-lead rate

The current schema lacks explicit "development" IDs, so uniqueness and freshness
are computed from citation/report groups:

- uniqueness credit: a cited source is the only cited source in a report
- freshness-lead credit: a cited source has the earliest published cited item in
  a report

Score formula:

`0.35 * hit_rate + 0.35 * citation_rate + 0.15 * uniqueness_rate + 0.15 * freshness_lead_rate`

All quality computation remains pure SQL/Python over stored rows with no model
calls and no automatic removal.

### Discovery Provider Seam

Add discovery settings with default OpenRouter web search:

```yaml
discovery:
  provider: openrouter_web
  model: null
```

Supported provider values:

- `openrouter_web`: current OpenRouter chat completions plus web plugin
- `perplexity`: Perplexity OpenAI-compatible chat completions using
  `PERPLEXITY_API_KEY`

Daily analyst calls continue to use OpenRouter. Weekly compaction keeps its
OpenRouter analyst client; source discovery may use a separate discovery client.
This preserves the one-analyst-call rule by not adding any new daily analyst
runtime calls.

### Embeddings Gate

Add an optional retrieval module and settings gate:

```yaml
retrieval:
  embeddings_enabled: false
  embeddings_provider: voyage
  embedding_model: voyage-3.5
  require_fts_failure: true
```

The embeddings path is inert unless:

- embeddings are enabled in settings
- an FTS insufficiency has been recorded
- optional sqlite-vec/Voyage dependencies are importable

When inactive or unavailable, retrieval continues to use FTS5. The upgrade path
must fail closed with clear operator errors rather than silently changing
retrieval behavior.

## Files

- Modify: `AGENTS.md`, `CLAUDE.md`
- Modify: `docs/agent-harness.md`, `docs/index.md`, `docs/architecture.md`,
  `docs/database.md`, `docs/patterns.md`, `docs/testing.md`,
  `docs/commands.md`, `docs/changelog.md`, `SPEC.md`
- Modify: `.codex/agents/*.toml`, `.codex/ci/*.md` as needed for harness
  alignment
- Modify: `TODO.md`, `session_ledger.json`
- Modify: `config/settings.yaml`, `pyproject.toml`
- Modify: `src/perpetual_analyst/config.py`
- Modify: `src/perpetual_analyst/store/db.py`
- Modify: `src/perpetual_analyst/store/models.py`
- Modify: `src/perpetual_analyst/quality.py`
- Modify: `src/perpetual_analyst/analyst/discovery.py`
- Modify: `src/perpetual_analyst/analyst/agent.py`
- Modify: `src/perpetual_analyst/weekly_run.py`
- Modify: `src/perpetual_analyst/cli.py`
- Create: `src/perpetual_analyst/analyst/candidates.py`
- Create: `src/perpetual_analyst/web.py`
- Create: `src/perpetual_analyst/retrieval/embeddings.py`
- Add tests for candidates, web UI, quality metrics, discovery providers, and
  embeddings gate.

## Validation

- TDD for each product behavior.
- Focused pytest files first, then full pytest when dependencies are available.
- `ruff check . --fix`, `ruff format .`, and `pre-commit run --all-files`
  before each commit when tooling is available.
- GitNexus impact before symbol edits and `gitnexus_detect_changes()` before
  commit when the repo is available in GitNexus.
- Security review is required because approval fetch validates and fetches
  operator-provided URLs.

## Current Environment Blockers To Record

- `.git` metadata is read-only in the current sandbox, blocking branch/worktree
  moves, commits, git notes, and PR submission.
- GitNexus MCP currently lists `Indonesia-Monitor` and `Nexus`, but not
  `perpetual-analyst`, so impact/detect changes cannot resolve this repo.
- The repo-local `.venv` was absent; dependency installation is blocked by
  restricted network access to PyPI.

These blockers do not change the spec; they determine which workflow steps can
be completed in this environment.
