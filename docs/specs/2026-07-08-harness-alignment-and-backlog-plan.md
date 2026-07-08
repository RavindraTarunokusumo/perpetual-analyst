# Harness Alignment And Backlog Implementation Plan

> **For agentic workers:** REQUIRED HANDOFF: Use Grok junior sessions through
> the non-interactive CLI (`grok -p ... --output-format json`) for bounded
> implementation tasks after harness alignment. Grok must not run git commands.
> The senior developer reviews diffs, validates, commits, notes, and cleans up.

**Goal:** Align the harness to the canonical 7-step Grok workflow and clear the
four backlog items without violating project invariants.

**Architecture:** Keep the core analyst runtime unchanged. Add operator-facing
source management around existing `source_candidates`, improve deterministic
quality scoring, make discovery provider choice configurable, and add an inert
embeddings gate that cannot alter retrieval until explicitly enabled.

**Tech Stack:** Python 3.12, SQLite, Typer, standard-library `http.server`,
OpenAI-compatible clients, optional sqlite-vec/Voyage imports.

---

### Task 1: Harness Alignment

**Files:**
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `docs/agent-harness.md`
- Modify: `.codex/agents/doc-updater.toml`
- Modify: `.codex/agents/test-plan-writer.toml`
- Modify: `.codex/ci/*.md`
- Modify: `SPEC.md`
- Modify: `docs/index.md`

Steps:

- [ ] Replace the workflow in `AGENTS.md` with the canonical 7-step workflow,
  retaining the eight core invariants and GitNexus MCP rules.
- [ ] Mirror the exact `AGENTS.md` workflow content into `CLAUDE.md`.
- [ ] Update `docs/agent-harness.md` to describe accepted specs in
  `docs/specs/`, Grok junior handoffs, senior-dev review, validation, Pre-PR,
  PR review, Post-PR archive, and reflection.
- [ ] Update harness agent/CI prompts so they reference `perpetual-analyst`
  rather than unrelated projects and require spec/TODO awareness.
- [ ] Update `SPEC.md` and `docs/index.md` to point to `docs/specs/` as the
  active spec workflow.
- [ ] Self-review for placeholders, contradictions, and unmatched AGENTS/CLAUDE
  content.

### Task 2: Source Candidate Approval Core

**Files:**
- Create: `src/perpetual_analyst/analyst/candidates.py`
- Modify: `src/perpetual_analyst/store/db.py`
- Modify: `src/perpetual_analyst/store/models.py`
- Add tests: `tests/test_source_candidates.py`

Steps:

- [ ] Write failing tests for URL validation rejecting private, localhost,
  credentialed, missing-host, and unsupported-scheme URLs.
- [ ] Write failing tests for approving a candidate: validated fetch, probation
  source insert, topic link insert, candidate `approved` status.
- [ ] Write failing tests for rejecting duplicate approvals and dismissing a
  candidate with a note.
- [ ] Implement idempotent source-candidate review columns using `_ensure_columns`.
- [ ] Implement SSRF-safe validation and redirect validation before fetch.
- [ ] Implement `approve_source_candidate` and `dismiss_source_candidate`.
- [ ] Run focused tests.

### Task 3: Web UI Dashboard

**Files:**
- Create: `src/perpetual_analyst/web.py`
- Modify: `src/perpetual_analyst/cli.py`
- Add tests: `tests/test_web_ui.py`
- Update docs: `docs/commands.md`, `docs/architecture.md`

Steps:

- [ ] Write failing tests for dashboard HTML showing pending candidates,
  source quality metrics, and probation/bottom-decile information.
- [ ] Write failing tests for POST approve/dismiss routes calling the candidate
  core functions and redirecting back to the dashboard.
- [ ] Implement a local `ThreadingHTTPServer` handler factory with injected DB
  path for tests.
- [ ] Add `analyst web --host 127.0.0.1 --port 8765`.
- [ ] Run focused tests.

### Task 4: Quality Metrics

**Files:**
- Modify: `src/perpetual_analyst/quality.py`
- Modify: `docs/database.md`, `docs/patterns.md`, `docs/architecture.md`
- Add tests: `tests/test_quality.py`

Steps:

- [ ] Write failing tests for uniqueness credit when a source is the only cited
  source in a report.
- [ ] Write failing tests for freshness-lead credit when a source has the
  earliest published cited item in a report.
- [ ] Update `SourceQuality` and `compute_source_quality` with the four-factor
  score formula.
- [ ] Preserve `bottom_decile` behavior and probation exclusion.
- [ ] Run focused tests.

### Task 5: Discovery Provider Seam

**Files:**
- Modify: `config/settings.yaml`
- Modify: `src/perpetual_analyst/config.py`
- Modify: `src/perpetual_analyst/analyst/agent.py`
- Modify: `src/perpetual_analyst/analyst/discovery.py`
- Modify: `src/perpetual_analyst/weekly_run.py`
- Add tests: `tests/test_config.py`, `tests/test_discovery.py`,
  `tests/test_weekly_run.py`

Steps:

- [ ] Write failing tests for default discovery provider config.
- [ ] Write failing tests for `make_client(provider="perplexity")` reading
  `PERPLEXITY_API_KEY` and Perplexity base URL.
- [ ] Write failing tests that Perplexity discovery does not include the
  OpenRouter plugin extra body.
- [ ] Implement discovery settings and discovery client selection.
- [ ] Keep daily/weekly analyst calls on OpenRouter unless explicitly passed a
  different provider.
- [ ] Run focused tests.

### Task 6: Embeddings Gate

**Files:**
- Modify: `pyproject.toml`
- Modify: `config/settings.yaml`
- Modify: `src/perpetual_analyst/config.py`
- Modify: `src/perpetual_analyst/store/db.py`
- Create: `src/perpetual_analyst/retrieval/embeddings.py`
- Add tests: `tests/test_embeddings.py`
- Update docs: `docs/database.md`, `docs/architecture.md`,
  `docs/patterns.md`

Steps:

- [ ] Write failing tests that embeddings are disabled by default.
- [ ] Write failing tests that embeddings cannot run when `require_fts_failure`
  is true and no FTS insufficiency has been recorded.
- [ ] Write failing tests that missing optional dependencies produce a clear
  unavailable result instead of changing retrieval behavior.
- [ ] Add optional dependencies and DB table for recorded FTS insufficiencies.
- [ ] Implement gated embedding availability and recording helpers.
- [ ] Run focused tests.

### Task 7: Pre-PR, Archive, Reflection

**Files:**
- Modify: `TODO.md`
- Modify: `session_ledger.json`
- Modify: `docs/iterations/archive/<date>-harness-alignment-and-backlog.md`
- Modify: `docs/insights.md`

Steps:

- [ ] Run full validation if dependencies are available; otherwise record
  blocked commands and run static syntax checks.
- [ ] Run GitNexus `detect_changes` if the repo becomes available in the MCP
  registry; otherwise record the unavailable repo result.
- [ ] Run `simplify`.
- [ ] Run doc update review.
- [ ] Run test-plan writer because behavior, state, API/UI, tests, and
  architecture changed.
- [ ] Run security review because approved URL fetch touches SSRF-sensitive
  network behavior.
- [ ] Commit each completed TODO sub-item and attach git notes if `.git` is
  writable.
- [ ] Submit PR and process Copilot/Grok reviews if git/GitHub operations are
  available.
- [ ] Archive completed TODO session and update workflow-only reflection after
  merge; leave TODO active if commit/PR/merge is blocked.
