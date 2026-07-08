# AGENTS.md / CLAUDE.md

Project: `perpetual-analyst`

**Follow the [Workflow](#workflow) strictly for feature implementation**. Do not start implementation until Steps 1-3 are complete. Before editing, state which step you are on. Before finishing, confirm Step 6 and Step 7.

Any change made to `AGENTS.md` must also be applied to `CLAUDE.md`.

## Project Map

- Product Spec: [SPEC.md](SPEC.md)
- Architecture: [docs/architecture.md](docs/architecture.md)
- Database / Persistence: [docs/database.md](docs/database.md)
- Patterns & Anti-patterns: [docs/patterns.md](docs/patterns.md)
- Testing: [docs/testing.md](docs/testing.md)
- Commands: [docs/commands.md](docs/commands.md)
- Agent Harness: [docs/agent-harness.md](docs/agent-harness.md)
- Spec Workflow: [docs/specs/README.md](docs/specs/README.md)
- Insights: [docs/insights.md](docs/insights.md)
- Full Index: [docs/index.md](docs/index.md)

## Core Invariants

**These must never be violated:**

1. **One analyst call per topic per day.** No multi-agent orchestration, no critic loops, no debate crews. The only permitted second model call per topic is the Haiku triage pass, which is a function, not an agent.
2. **Memory is structural, not behavioral.** Budgets are enforced by the context assembler truncating by importance/recency, not by prompting the model to "write less." `build_memory_context()` must always respect token budgets.
3. **Theses are never silently edited.** Every revision writes a `thesis_updates` row with before/after confidence and a stated reason. `<=7 active theses per topic` is a hard constraint.
4. **`nothing_significant: true` is a first-class output.** Never treat it as an error or omit it from the schema. Topics with nothing to report get one line.
5. **All memory writes are transactional.** The analyst call returns a bundle (observations, thesis updates, dossier edits). All writes either succeed together or none succeed; no partial state.
6. **No feature earns its place without justifying against:** *"does this make the analyst's reasoning measurably better?"*
7. **Runtime secrets must not be logged.** `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `PERPLEXITY_API_KEY`, and `TELEGRAM_BOT_TOKEN` must never appear in logs or stdout.
8. **`content_hash` is the dedupe key for items.** Inserting duplicate content must silently skip, never raise.

## Code Graph / Repo Map

This repo is indexed by **GitNexus** when available. See the GitNexus section below for all rules and resources.

Rules:
- Do not rebuild the graph while files are being modified.
- Only rebuild on a clean working tree.
- Use the graph as a snapshot, not a live source of truth.
- Query the graph first, then read files directly.
- If the MCP registry does not expose this repo, record that blocker and fall back to direct caller/source reads.

## Workflow

1. **Preamble** — Work in a dedicated local branch or worktree. Activate the project environment from `.venv` at the repo root. Confirm repo status before editing. Read `docs/insights.md` and the Workflow Rules. Identify the active accepted spec path under `docs/specs/`.

2. **Repo Map / GitNexus** — Read the GitNexus section at the start of every session. Run or query the available code graph/index if present. Use docs and graph output to understand the areas named by the active spec.

3. **Planning** — Read `AGENTS.md`, `docs/index.md`, the active spec, and relevant technical docs. If no accepted spec exists, use the `brainstorming` skill to create or refine one before implementation planning. Produce a concise plan and scope derived from the accepted spec. Do not edit implementation files until the plan is accepted unless the user explicitly granted Autopilot Mode.

4. **Implementation** — Log spec-derived tasks and sub-items in `TODO.md` before editing (include the active spec path). Implement each task by delegating to a **Grok junior subagent as the implementer** via the non-interactive CLI, one ephemeral session per task where practical. See [Grok Build Implementation/Review Handoff](#grok-build-implementationreview-handoff). After each Grok handoff, the senior developer independently reviews the diff, normalizes output, validates with lint/typecheck/tests before committing, then deletes the ephemeral Grok session directory. If Grok is unavailable, record the reason and fall back only after updating TODO.md.

5. **Submit PR** — Use `.github/pull_request_template.md`. Fill out summary, spec path, scope, test plan, risk, rollback, docs, backlog, and targeted UI checks. Delegate PR code review (and security review where applicable) to Grok via the same non-interactive handoff; capture `sessionId`, process findings, clean up the session directory, and address findings with the `receiving-code-review` skill if available. Run review agents **before** opening the PR; fix blocking findings first.

6. **Post-PR** — Once the PR has been merged, ensure `TODO.md` contains only active or future work. Archive completed TODO sessions into `docs/iterations/archive/`, including the related spec path. These commits are pushed **directly to `main`** (fast-forward only). Tag completed sub-items with commit hashes and the session with the merge ID. Add session lessons to `docs/insights.md`.

7. **Reflection** — Conclude the session by recording useful workflow lessons in `docs/insights.md` (commands, tools used, skills invoked, MCPs, scripts created, workflow improvements, recurring failure modes, skills worth adding or improving). Do not include feature-specific implementation details. Report the reflection to the user in chat and wait for explicit permission before deleting the worktree and branch. This commit is pushed **directly to `main`**.

## Autopilot Mode

Autopilot Mode allows implementation to proceed through Steps 3-5 without pausing for plan acceptance between each step.

Rules:
- Autopilot Mode must be explicitly granted by the user in the current session; it is never assumed, never carried over from a prior session, and is never granted by a PM/chat-relay instruction alone.
- Autopilot Mode does not waive the accepted-spec requirement.
- Autopilot Mode does not waive TODO logging, Grok handoffs, specific staging, per-sub-item commits, git notes, GitNexus checks, or Post-PR/Reflection validation.
- Autopilot Mode does not authorize destructive git operations.
- If discovery during implementation contradicts the plan or spec, pause Autopilot and report back.

## Workflow Rules

1. Every TODO sub-item should land as its own commit.
2. Any extension or modification to the task must update the active spec first, then be logged in `TODO.md`.
3. Use specific staging; never use `git add -A`.
4. Never force-push, reset `--hard`, merge, or amend unless explicitly asked.
5. Keep comments sparse. Prefer clear naming over clever abstractions. Avoid compatibility shims unless explicitly required.
6. Do not leave important conclusions only in chat memory; write them to docs.
7. A chat prompt is not implementation authority by itself.
8. Do not implement from a spec with unresolved blocking open questions.
9. When pre-commit fails only on untouched files, note it as pre-existing.
10. After context compaction, run `git status` first.
11. Commit any files written by subagents/doc-updater/security-review immediately.
12. `gitnexus_impact` requires the exact symbol name.

## Grok Build Implementation/Review Handoff

(The full detailed section from the previous perpetual-analyst version — headless Grok CLI with `--effort high --yolo --output-format json`, self-contained prompts, senior dev review responsibility, cleanup command, parallelism rules, etc. — is retained here without change.)

## Pre-Commit Checks

```bash
ruff check . --fix
ruff format .
pytest
pre-commit run --all-files
```

(If tools are missing, report clearly and record in session_ledger.json.)

## GitNexus — Code Intelligence

(The full GitNexus section from the previous perpetual-analyst AGENTS.md is retained here, including the table of MCP endpoints, Always Do / Never Do rules, and CLI skill references.)

## Reflection

After every completed session, record useful workflow lessons in `docs/insights.md`. Do not include feature-specific implementation details. Cover commands executed, tools used, skills invoked, MCPs accessed, scripts created, workflow improvements, recurring failure modes, and skills worth adding or improving. Report the reflection to the user in chat and wait for explicit permission before deleting the worktree and branch.
