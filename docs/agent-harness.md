# Agent Documentation Harness

This repository uses a layered documentation and skill harness for safe,
spec-driven agentic development.

## Purpose

Give every agent one clear path to:

- preserve project invariants
- understand architecture and persistence
- identify the accepted spec
- delegate bounded implementation work to Grok juniors
- validate and review changes before commits
- keep docs, TODOs, git notes, and session memory synchronized

## Layered Documentation Model

### Layer A - Repo Contract

Files: `AGENTS.md`, `CLAUDE.md`

- 7-step workflow
- branch/worktree and environment expectations
- Core Invariants
- GitNexus impact/detect-changes rules
- Grok junior handoff contract
- commit, Pre-PR, PR, Post-PR, and reflection rules

`AGENTS.md` and `CLAUDE.md` must stay mirrored.

### Layer B - Specs And Plans

Files: `docs/specs/`

- accepted feature specs
- implementation plans derived from accepted specs
- active spec path referenced from `TODO.md`

Implementation is never driven by chat prompts alone. A prompt can supply an
accepted spec or start spec creation/refinement, but code changes need an active
spec under `docs/specs/`.

Historical pre-canonical specs remain under `docs/superpowers/specs/` and
`docs/superpowers/plans/`.

### Layer C - Domain And System Context

Files: `docs/architecture.md`, `docs/database.md`, `docs/patterns.md`,
`docs/testing.md`, `docs/commands.md`, `SPEC.md`

- technical truth
- data model and memory tiers
- invariants and anti-patterns
- commands and debugging workflows
- product architecture

### Layer D - Task Skills

Canonical root: `.codex/skills/<skill-name>/`

Primary skills:

- `brainstorming` - create or refine specs when no accepted spec exists
- `writing-plans` - produce implementation plans from accepted specs
- `test-driven-development` - write failing tests before behavior changes
- `simplify` - pre-PR behavior-preserving simplification review
- `security-review` - focused diff review for security-sensitive changes
- `receiving-code-review` - verify and process external review findings
- `test-plan-writer` - post-implementation test plan for meaningful changes

Fallback skill:

- `subagent-driven-development` - use only if Grok is unavailable or blocked,
  and record the fallback reason in `TODO.md`.

Agent configs: `.codex/agents/`

- `doc-updater.toml` - documentation freshness after recent changes
- `test-plan-writer.toml` - structured test plan writer

CI prompt docs: `.codex/ci/`

- code-health and documentation audit/remediation prompts aligned to
  `perpetual-analyst`

### Layer E - Work Tracking And Change History

Files: `TODO.md`, `session_ledger.json`, `docs/iterations/archive/`,
`docs/changelog.md`, `docs/insights.md`

- active work (`TODO.md`)
- session status and blockers (`session_ledger.json`)
- completed work (`docs/iterations/archive/`)
- behavior and architecture changes (`docs/changelog.md`)
- workflow lessons (`docs/insights.md`)

## Recommended Navigation Order

1. Read `AGENTS.md`.
2. Read the active accepted spec under `docs/specs/`.
3. Read `TODO.md` for the current session entry.
4. Query GitNexus if this repo is available in the MCP registry.
5. Read `docs/index.md`.
6. Read `docs/architecture.md` for module boundaries.
7. Read `docs/database.md` if touching persistence.
8. Read `docs/patterns.md` for invariants and anti-patterns.
9. Use Grok non-interactive handoffs for implementation tasks.
10. Review diffs directly as the senior developer.
11. Validate (`ruff`, `pytest`, `pre-commit`) when tooling is available.
12. Run `simplify`, docs update review, test-plan writer, and security review
    when required.
13. Prepare PR using `.github/pull_request_template.md`.
14. Archive completed TODO work after merge and write workflow-only reflection.

## Grok Junior Handoff Contract

Use headless JSON output:

```bash
HOME=/root grok -p "<self-contained task instructions>" -m grok-composer-2.5-fast --effort high --yolo --output-format json
```

Every implementation prompt must include:

- active spec path
- relevant TODO item
- exact file scope
- acceptance criteria
- validation commands
- "do not run git commands"
- request for final summary with files changed, checks run, blockers, and
  `sessionId`

The senior developer must:

- parse JSON and record the `sessionId`
- inspect the diff directly
- run validation independently
- stage specific files only
- commit, attach notes, update TODO, and clean up the Grok session directory

## Ownership And Source Of Truth

- Policy source of truth: `AGENTS.md` mirrored to `CLAUDE.md`
- Spec source of truth: `docs/specs/`
- Work source of truth: `TODO.md`
- Session status source of truth: `session_ledger.json`
- Technical source of truth: `docs/` and `SPEC.md`
- Skill source of truth: `.codex/skills/`

If duplicates exist, update the canonical content first, then mirror.

## Update Rules

- If workflow changes, update `AGENTS.md`, mirror to `CLAUDE.md`, and update
  this file.
- If source behavior changes, update relevant docs in the same iteration.
- If schema changes, update `docs/database.md`, tests, and migration notes.
- If repeated tasks emerge, create or revise a skill.
- Keep skills focused and composable.
- Keep `TODO.md` active/future only; archive completed work after merge.
