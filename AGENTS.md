# AGENTS.md

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

1. (Preamble) Ensure you're in a dedicated local branch/worktree under `.worktree/<session-name>` and activate the virtual environment `.venv` located in the root directory. Run `pip install -e .` so the package imports without a per-command `PYTHONPATH`. Read the `docs/insights.md` file and the [Workflow Rules](#workflow-rules).
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
11. When a command needs a multi-line body (commit message, PR body, review comment), write the body to a file with the Write tool and pass it via `--body-file`/`-F`, then run `gh`/`git` as its own standalone command. Never chain a here-string with `gh` and `Remove-Item` in one compound command — it can fail silently and skip the action.
12. When parallel subagent dispatch fails on a session limit, fall back to doing the work inline in the main context rather than retrying the dispatch.

### Working in worktrees

- Never run `npx gitnexus analyze` inside a worktree — it registers the worktree as a separate repo and rewrites the GitNexus block in `AGENTS.md`/`CLAUDE.md`. Reindex from the primary directory only. A stale-index warning is harmless for LOW-risk leaf additions.
- Run `pre-commit` with the root `.pre-commit-config.yaml` from the **root** directory, not the worktree CWD (or set `PRE_COMMIT_ALLOW_NO_CONFIG=1`).
- `git checkout main` fails from a worktree (main is checked out in the primary dir). Do post-PR work on main from the primary directory with `git -C <primary-path> ...` (e.g. `git -C <primary> pull --ff-only origin main`).

### Pre-PR

Use the following as the final steps before submitting a PR:

- `/simplify` (skill)
- `doc-updater` (subagent)
- **Bounded live validation** — REQUIRED for any phase that touches external APIs, network, or file/stdout IO. Run the real pipeline (e.g. `analyst run --dry-run`) against a small/bounded input; mocks validate the mock, not the contract. If a feed or call is too slow, shrink its input (mark heavy feeds `last_fetched_at = now`) rather than skipping the check.

**Invoke the following subagents IF changes affect security or significant architectural changes (or explicitly stated). Always cite your justification on why you decide to invoke them:**

- `test-plan-writer` (subagent)
- `security-review` (skill)

Any fix made in response to a review is itself unreviewed code: after addressing review findings, run a focused review over the **fix delta** (not just the original branch) before proceeding.

### Submit PR

- Fill out the **[Template](.github/pull_request_template.md)**.
- Submit the PR and wait for about 20m for the GitHub Copilot Code Review agent to finish writing the reviews.
- If Copilot is unavailable, dispatch a substitute Opus `/code-review` over the whole branch and treat its findings the same way.
- Use the `/receiving-code-review` skill to address the issues in the Copilot Code Review.
- Merge with a **merge commit, not squash**, so per-commit SHAs stay verifiable in `git log` for archive tagging.

### Reflection

After every session completion, you reflect on how the workflow pertaining to the workflow and agent harness - the commands you executed (and which failed consistently), the tools you used, skills invoked, MCP accessed, etc. **Do not include anything feature-specific**. For example, when the Graphify output is too verbose or if certain powershell commands keeps failing. This is not about the features you implemented, but about *how* you implemented them. Write this down in [Insights](docs/insights.md) and then report it to the user in chat. Wait until user gives explicit permission to conclude the session.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **perpetual-analyst** (1163 symbols, 1374 relationships, 8 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/perpetual-analyst/context` | Codebase overview, check index freshness |
| `gitnexus://repo/perpetual-analyst/clusters` | All functional areas |
| `gitnexus://repo/perpetual-analyst/processes` | All execution flows |
| `gitnexus://repo/perpetual-analyst/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
