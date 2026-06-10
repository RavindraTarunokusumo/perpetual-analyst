# Agent Documentation Harness

This repository uses a layered documentation and skill harness for safe agentic development.

## Purpose

Give every agent one clear path to:

- understand repo rules
- understand architecture
- pick the right skill
- execute safely
- validate changes
- keep docs synchronized
- preserve session memory

## Layered Documentation Model

### Layer A — Repo Contract

File: `AGENTS.md`

- allowed and forbidden actions
- branch/worktree workflow
- commit/test/lint expectations
- PR expectations
- project-specific invariants
- links to deeper docs

### Layer B — Domain and System Context

Files: `docs/architecture.md`, `docs/database.md`, `docs/patterns.md`, `docs/testing.md`, `docs/commands.md`

- technical truth
- data model and memory tiers
- invariants and anti-patterns
- commands and debugging workflows

### Layer C — Task Skills

Canonical root: `.codex/skills/<skill-name>/`

Available skills:
- `brainstorming` — structured planning and design exploration
- `writing-plans` — produce a concise implementation plan
- `subagent-driven-development` — break tasks into subagent-executable pieces
- `dispatching-parallel-agents` — parallel agent dispatch
- `test-driven-development` — TDD workflow
- `test-plan-writer` — structured test plan after implementation
- `simplify` — pre-PR simplification review
- `receiving-code-review` — respond to code review feedback
- `security-review` — security audit for sensitive changes

Agent configs: `.codex/agents/`
- `doc-updater.toml` — update docs after code changes
- `test-plan-writer.toml` — structured test plan writer

CI workflows: `.codex/ci/`
- `weekly-codebase-checkup.md`
- `code-health-remediation.md`
- `doc-freshness-audit.md`
- `doc-freshness-remediation.md`

### Layer D — Work Tracking and Change History

Files: `TODO.md`, `docs/iterations/active/`, `docs/iterations/archive/`, `docs/changelog.md`, `docs/insights.md`

- active work (TODO.md)
- completed work (archive/)
- why changes happened (changelog.md)
- session lessons (insights.md)

## Recommended Navigation Order

1. Read `AGENTS.md`.
2. Read `docs/index.md`.
3. Read `docs/architecture.md` for module boundaries.
4. Read `docs/database.md` if touching persistence.
5. Select the matching skill if available.
6. Implement through `TODO.md`.
7. Validate (`ruff check`, `ruff format`, `pytest`).
8. Run `simplify` skill.
9. Run `doc-updater` agent.
10. Prepare PR using `.github/pull_request_template.md`.
11. Archive completed work.

## Ownership and Source of Truth

- Policy source of truth: `AGENTS.md`
- Work source of truth: `TODO.md`
- Technical source of truth: `docs/`
- Architecture source of truth: `SPEC.md` (authoritative design) and `docs/architecture.md` (living summary)
- Skill source of truth: `.codex/skills/`

If duplicates exist, update canonical content first, then mirror.

## Update Rules

- If source behavior changes, update relevant docs in the same iteration.
- If workflow changes, update `AGENTS.md`.
- If repeated tasks emerge, create or revise a skill.
- Keep skills focused and composable.
- After Phase 1 completes, update `docs/architecture.md` to reflect actual implementation details.
