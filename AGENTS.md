# AGENTS.md

Project: `perpetual-analyst`

Follow the 7-Step Workflow strictly for feature implementation. Do not start implementation until Steps 1–5 are complete unless the user explicitly authorizes a different flow. Before editing, state which step you are on. Before finishing, confirm Step 6 and Step 7.

## Project Map

- Architecture: [docs/architecture.md](docs/architecture.md)
- Database / Persistence: [docs/database.md](docs/database.md)
- Patterns & Anti-patterns: [docs/patterns.md](docs/patterns.md)
- Testing: [docs/testing.md](docs/testing.md)
- Commands: [docs/commands.md](docs/commands.md)
- Agent Harness: [docs/agent-harness.md](docs/agent-harness.md)
- Full Index: [docs/index.md](docs/index.md)
- Spec: [SPEC.md](SPEC.md)

## Core Invariants

**These must never be violated:**

1. **One analyst call per topic per day.** No multi-agent orchestration, no critic loops, no debate crews. The only permitted second model call per topic is the Haiku triage pass, which is a function, not an agent.
2. **Memory is structural, not behavioral.** Budgets are enforced by the context assembler truncating by importance/recency — not by prompting the model to "write less." `build_memory_context()` must always respect token budgets.
3. **Theses are never silently edited.** Every revision writes a `thesis_updates` row with before/after confidence and a stated reason. `≤7 active theses per topic` is a hard constraint.
4. **`nothing_significant: true` is a first-class output.** Never treat it as an error or omit it from the schema. Topics with nothing to report get one line.
5. **All memory writes are transactional.** The analyst call returns a bundle (observations, thesis updates, dossier edits). All writes either succeed together or none succeed — no partial state.
6. **No feature earns its place without justifying against:** *"does this make the analyst's reasoning measurably better?"*
7. **Runtime secrets must not be logged.** `ANTHROPIC_API_KEY` and `TELEGRAM_BOT_TOKEN` must never appear in logs or stdout.
8. **`content_hash` is the dedupe key for items.** Inserting duplicate content must silently skip, never raise.

## Code Graph / Repo Map

If a code graph or dependency map exists, use it before touching unfamiliar code. Only rebuild on a clean working tree. Query the graph first, then read files directly.

## 7-Step Workflow

1. **Preamble**
   - Work in a dedicated local branch or worktree.
   - Activate the project environment: `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate`.
   - Confirm repo status before editing.

2. **Repo Map**
   - Run or query the available code graph/index if present.
   - Read `docs/architecture.md` for module boundaries before touching unfamiliar code.

3. **Planning**
   - Read `AGENTS.md`, `docs/index.md`, and the relevant technical docs.
   - Use the `brainstorming` skill for implementation planning if available.
   - Use the `writing-plans` skill to produce a concise plan and scope.
   - Do not edit until the plan is accepted unless the user explicitly granted autonomous execution.

4. **Implementation**
   - Log tasks and sub-items in `TODO.md` before editing.
   - Use the `subagent-driven-development` skill where applicable.
   - Keep edits focused. Do not add features beyond the stated task.

5. **Commit**
   - Run pre-commit checks before each commit (see below).
   - Each meaningful TODO sub-item should land as its own commit.
   - Use specific staging; never use `git add -A`.
   - Attach a git note using `.github/git_notes_template.md`.
   - Mark completed TODO sub-items with the commit hash.

6. **Pre-PR**
   - Run the `simplify` skill if available.
   - Run the `doc-updater` agent or subagent if available.
   - Invoke `test-plan-writer` if behavior, state, API, tests, or architecture changed.
   - Invoke `security-review` if the change touches the Anthropic API key, Telegram token, network calls, or user input.
   - Run full validation.

7. **Submit PR**
   - Use `.github/pull_request_template.md`.
   - Fill out summary, scope, test plan, risk, rollback, docs, backlog.
   - Address automated review with the `receiving-code-review` skill if available.
   - Notify the user when all steps are complete.

## Pre-Commit Checks

```bash
ruff check . --fix
ruff format .
pytest
```

If a tool is missing or unavailable, report it clearly.

## Pre-PR

Before submitting a PR:

- run simplification review (`simplify` skill)
- update docs (`doc-updater` agent)
- run relevant tests
- run full tests when shared state, architecture, or cross-module behavior changed
- run security review when touching secrets, API calls, or network I/O
- ensure `TODO.md` is current

## Post-PR

- `TODO.md` contains active or future work only.
- Archive completed TODO sessions into `docs/iterations/archive/`.
- Tag completed sub-items with commit hashes.
- Add session lessons to `docs/insights.md`.

## Workflow Rules

1. Every TODO sub-item should land as its own commit.
2. Any extension or modification to the task must be logged in `TODO.md`.
3. Use specific staging, never `git add -A`.
4. Never force-push, reset `--hard`, merge, or amend unless explicitly asked.
5. Keep comments sparse — only when the WHY is non-obvious.
6. Prefer clear naming over clever abstractions.
7. Avoid compatibility shims unless explicitly required.
8. Do not leave important conclusions only in chat memory; write them to docs.
9. Do not add multi-agent patterns. See invariants above.

## Reflection

After every completed session, record useful lessons in `docs/insights.md`:

- tools used
- scripts created
- workflow improvements
- recurring failure modes
- skills worth adding or improving
