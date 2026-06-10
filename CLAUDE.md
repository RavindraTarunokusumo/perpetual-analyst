# CLAUDE.md

Project: `perpetual-analyst`

**Follow the [Workflow](#workflow) strictly for feature implementation**. Do not start implementation until Steps 1-5 are complete. Before editing, show which step you are on. Before finishing, confirm Step 6 and Step 7. Finally, do Step 8 and 9 to wrap up the session.

Any change made to `AGENTS.md` should also be applied to `CLAUDE.md`.

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

## Workflow

1. (Preamble) Ensure you're in a dedicated local branch/worktree under `.worktree/<session-name>` and activate the virtual environment `.venv` located in the root directory. Read the `docs/insights.md` file and the [Workflow Rules](#workflow-rules).
2. (GitNexus) Read the [GitNexus](#gitnexus--code-intelligence) section at the start of every session.
3. (Planning) Brainstorm implementation plan and spec using the `/brainstorming` skill; read the docs (see [Project Map](#project-map)) and use GitNexus as your primary means to understand the codebase.
4. (Implementing) After you get permission from user, log tasks and sub-items in `TODO.md` first before you start, then use the `/subagent-driven-development` skill to implement the tasks.
5. (Commit) Run `pre-commit run --all-files` before each commit and attach a git note afterwards using the [template](.github/git_notes_template.md). Cross each sub-items and items once done.
6. (Pre-PR) Once every items are crossed, do the [Pre-PR](#pre-pr) workflow.
7. (Submit PR) Finally, follow the instructions in the [Submit PR](#submit-pr) workflow and notify the user once every step have been completed.
8. (Post-PR) Archive completed TODO items from `TODO.md` into `docs/iterations/archive/` and ensure each subitem in the TODO are tagged with the commmit hash and each session are tagged with the merge ID. `TODO.md` should only contain **active or future** work only.
9. (Reflection) Conclude the session by doing the [Reflection](#reflection) exercise. After receiving confirmation from the user, delete the worktree and branch.

### Workflow Rules

1. Every TODO sub-item should land as its own commit.
2. Any extension or modification to the task should be logged in the TODO.
3. Use specific staging, never `git add -A`.
4. Never force-push, reset `--hard`, merge or amend unless explicitly asked.
5. Keep comments sparse, naming clear, abstractions minimal, and avoid compatibility shims.
6. When `pre-commit run --all-files` fails only on files you did not touch, note it as pre-existing and proceed — do not attempt workarounds that affect other files.
7. After subscribing to PR activity, wait for Copilot Code Review (allow ~20 min) and address all findings before marking the session complete.
8. After context compaction resumes, run `git status` before any other action — the summary describes intent, not exact commit state.
9. Commit any files written by subagents (doc-updater, security-review, etc.) immediately; do not advance the workflow with a dirty tree.
10. `gitnexus_impact` requires the exact function/class name, not the module or file name. Use the symbol name as indexed (e.g. `answer_chat`, not `routes_chat`).

### Pre-PR

Use the following as the final steps before submitting a PR:

- `/simplify` (skill)
- `doc-updater` (subagent)

**Invoke the following subagents IF changes affect security or significant architectural changes (or explicitly stated). Always cite your justification on why you decide to invoke them:**

- `test-plan-writer` (subagent)
- `security-review` (skill)

### Submit PR

- Fill out the **[Template](.github/pull_request_template.md)**.
- Submit the PR and wait for about 20m for the GitHub Copilot Code Review agent to finish writing the reviews.
- Use the `/receiving-code-review` skill to address the issues in the Copilot Code Review.

### Reflection

After every session completion, you reflect on how the workflow pertaining to the workflow and agent harness - the commands you executed (and which failed consistently), the tools you used, skills invoked, MCP accessed, etc. **Do not include anything feature-specific**. For example, when the Graphify output is too verbose or if certain powershell commands keeps failing. This is not about the features you implemented, but about *how* you implemented them. Write this down in [Insights](docs/insights.md) and then report it to the user in chat. Wait until user gives explicit permission to conclude the session.