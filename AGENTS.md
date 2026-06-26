# AGENTS.md

Project: `perpetual-analyst`

**Follow the [Workflow](#workflow) strictly for feature implementation**. Do not start implementation until Steps 1-3 are complete. Before editing, show which step you are on.

Any change made to `AGENTS.md` should also be applied to `CLAUDE.md`.

## Project Map

**Add more when needed**

- Architecture: [docs/architecture.md](docs/architecture.md)
- Database / Persistence: [docs/database.md](docs/database.md)
- Patterns: [docs/patterns.md](docs/patterns.md)
- Testing: [docs/testing.md](docs/testing.md)
- Commands: [docs/commands.md](docs/commands.md)
- Agent Harness: [docs/agent-harness.md](docs/agent-harness.md)
- Full Index: [docs/index.md](docs/index.md)

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

If a code graph, dependency map, or architecture index exists, use it before touching unfamiliar code.

Rules:

- Do not rebuild the graph while files are being modified.
- Only rebuild on a clean working tree.
- Use the graph as a snapshot, not a live source of truth.
- Query the graph first, then read files directly.

## Workflow

1. (Preamble) Ensure you're in a dedicated local branch/worktree under `.worktree/<session-name>` and activate the virtual environment `.venv` located in the root directory. Read the `docs/insights.md` file and the [Workflow Rules](#workflow-rules).
2. (GitNexus) Read the [GitNexus](#gitnexus--code-intelligence) section at the start of every session.
3. (Planning) For feature implementation, brainstorm implementation plan using the `/brainstorming` skill; read the docs (see [Project Map](#project-map)) and use GitNexus as your primary means to understand the codebase. For debugging or minor patching, skip this step.
4. (Implementing) Log tasks and sub-items in `TODO.md` first, then use the dedicated [Grok Build Handoff](#grok-build-handoff) for all implementation. ChatGPT/Claude may plan, decompose, review, verify, and orchestrate, but Grok Build owns the actual coding work: tests, implementation edits, and fix edits. Run `pre-commit run --all-files` before each commit and attach a git note afterwards using the [template](.github/git_notes_template.md). Cross each sub-items and items once done. Before opening the PR, run a **bounded live validation** for any change that touches external APIs, network, or file/stdout IO — exercise the real pipeline (e.g. `analyst run --dry-run`) against a small/bounded input; mocks validate the mock, not the contract. If a feed or call is too slow, shrink its input rather than skipping the check.
5. (Submit PR) Finally, follow the instructions in the [Submit PR](#submit-pr) workflow — using non-interactive `grok -p` commands where possible to trigger reviews — and notify the user once every step has been completed. If Grok fails, spawn native subagents as a fallback.
6. (Post-PR) Update documentation files once the PR has been merged and archive completed TODO items from `TODO.md` into `docs/iterations/archive/`; ensure each subitem in the TODO are tagged with the commmit hash and each session are tagged with the merge ID - `TODO.md` should only contain **active or future** work only.
7. (Reflection) Conclude the session by doing the [Reflection](#reflection) exercise. After receiving confirmation from the user, delete the worktree and branch.

### Workflow Rules

1. Every TODO sub-item should land as its own commit.
2. Any extension or modification to the task should be logged in the TODO.
3. Use specific staging, never `git add -A`.
4. Never force-push, reset `--hard`, merge or amend unless explicitly asked.
5. Keep comments sparse, naming clear, abstractions minimal, and avoid compatibility shims.
6. When `pre-commit run --all-files` fails only on files you did not touch, note it as pre-existing and proceed — do not attempt workarounds that affect other files.
7. After submitting the PR, delegate the code review (and optional security review) to Grok as ephemeral subagent sessions via the non-interactive CLI (`grok -p ... --output-format json --yolo`). Capture the `sessionId` from the JSON result, process the review output/side-effects (e.g. PENDING review posts), then immediately delete the corresponding `~/.grok/sessions/.../<sessionId>` directory for that security-review or code-review subagent task. See the detailed examples and cleanup logic in the [Submit PR](#submit-pr) section. Do not rely on GitHub Copilot Code Review. Rigorously address findings using the reception protocol.
8. After context compaction resumes, run `git status` before any other action — the summary describes intent, not exact commit state.
9. Commit any files written by subagents immediately; do not advance the workflow with a dirty tree. For Grok-based subagents (security-review, bundled code-review, etc.), always capture the sessionId via `--output-format json` and delete the ephemeral chat session directory after the delegation completes and findings are processed.
10. When a command needs a multi-line body (commit message, PR body, review comment), write the body to a file with the Write tool and pass it via `--body-file`/`-F`, then run `gh`/`git` as its own standalone command. Never chain a here-string with `gh` and `Remove-Item` in one compound command — it can fail silently and skip the action.

### Grok Build Handoff

Use Grok Build for all feature implementation after Steps 1-3 are complete. ChatGPT/Claude remains the planner and reviewer; Grok Build is the implementer.

Before starting Grok Build, the orchestrating agent must provide:

- The approved plan or spec, with the exact `TODO.md` item/sub-item to implement.
- Relevant Core Invariants, GitNexus findings, impact-analysis blast radius, and docs read.
- Expected files/modules, tests to add or update, validation commands, and bounded live-validation requirements.
- Commit expectations: one TODO sub-item per commit, specific staging only, pre-commit before commit, git note after commit.

During implementation:

- Grok Build writes the tests, implementation edits, and review/fix edits. ChatGPT/Claude should not hand-code implementation unless the user explicitly approves a fallback because Grok Build is unavailable or repeatedly fails.
- The orchestrating agent reviews Grok Build's diff, verifies that it matches the plan and invariants, runs required checks, and sends any necessary fix requests back through a new Grok Build handoff.
- If a review finding requires code changes, route the fix through Grok Build as well, then re-review the fix delta before proceeding.

For Grok CLI delegations, use non-interactive commands so the handoff is reproducible and leaves no long-lived chat state:

```powershell
$prNum = gh pr view --json number -q .number
$prompt = "Use /bundled:review --pr #$prNum. The skill should post a PENDING GitHub review. After it completes, provide a very brief summary of what was done."
$json = grok -p $prompt --yolo --output-format json
$reviewSummary = ($json | ConvertFrom-Json).text
$sessionId = ($json | ConvertFrom-Json).sessionId

# Main agent processes $reviewSummary and any side-effects before cleanup.
Get-ChildItem -Path "$env:USERPROFILE\.grok\sessions" -Recurse -Directory -Filter $sessionId |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
```

Grok CLI argument rules:

- `-p` / `--single`: headless single-turn mode; creates an ephemeral chat session without opening an interactive terminal/TUI.
- `--yolo` / `--always-approve`: auto-approves delegated tools so the handoff runs unattended.
- `--output-format json`: returns structured output with `text` and `sessionId`; always capture `sessionId` before cleanup.
- Delete `~/.grok/sessions/.../<sessionId>` after processing the result or side-effects. The recursive exact-ID filter is reliable across worktrees.
- The invoked Grok skill does the actual delegated work, such as diff collection, reviewer persona, and posting PENDING GitHub reviews. The `grok -p` command is the delegation and cleanup wrapper.

### Working in worktrees

- Never run `npx gitnexus analyze` inside a worktree — it registers the worktree as a separate repo and rewrites the GitNexus block in `AGENTS.md`/`CLAUDE.md`. Reindex from the primary directory only. A stale-index warning is harmless for LOW-risk leaf additions.
- Run `pre-commit` with the root `.pre-commit-config.yaml` from the **root** directory, not the worktree CWD (or set `PRE_COMMIT_ALLOW_NO_CONFIG=1`).
- `git checkout main` fails from a worktree (main is checked out in the primary dir). Do post-PR work on main from the primary directory with `git -C <primary-path> ...` (e.g. `git -C <primary> pull --ff-only origin main`).
- On teardown, run `pip install -e .` from the **primary** directory before deleting the worktree: it re-points the editable install (and the `analyst` console script) back to the primary `src/` and releases the file handle that otherwise blocks worktree directory removal on Windows/OneDrive.

### Submit PR

1. Fill out the **[Template](.github/pull_request_template.md)** and submit the PR (capture the PR number/URL, e.g. via `gh pr create --json number,url`).

2. (Optional) If the changes affect security (or explicitly stated), delegate a non-interactive security review to a Grok subagent (ephemeral session). Always cite justification. Capture the session ID and clean it up afterwards so the review chat session is deleted. PowerShell example:
   ```powershell
   $prNum = gh pr view --json number -q .number
   $prompt = "Use the /security-review skill on PR #$prNum. Report only HIGH-confidence newly introduced vulnerabilities from the diff."
   $json = grok -p $prompt --yolo --output-format json
   $reviewText = ($json | ConvertFrom-Json).text
   $sessionId = ($json | ConvertFrom-Json).sessionId

   # Main agent (Claude Code etc.) processes $reviewText here (e.g. incorporate findings, address via receiving-code-review logic)

   # Delete the ephemeral Grok subagent chat session created for this review
   Get-ChildItem -Path "$env:USERPROFILE\.grok\sessions" -Recurse -Directory -Filter $sessionId |
       Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
   ```

3. Non-interactively generate the main professional code review by delegating to the Grok bundled reviewer as a subagent. Use the CLI command pattern and cleanup rules in [Grok Build Handoff](#grok-build-handoff): invoke `/bundled:review --pr #<number>`, capture `sessionId` from `--output-format json`, process the result and PENDING review side-effects, then delete the ephemeral Grok session.

- Rigorously address the review findings before considering the task complete. Use the reception protocol defined in [Skills/receiving-code-review/SKILL.md](Skills/receiving-code-review/SKILL.md):
  - Read the full feedback first.
  - Verify each item technically against the actual codebase.
  - Push back (with clear technical reasoning) on items that seem incorrect, unclear, or low-value.
  - Implement one change at a time and test it.
  - Avoid performative agreement ("You're right!", "Great catch!"); just state what was done or ask for clarification.
  - After addressing findings, re-review the **fix delta** — fixes made in response to a review are themselves unreviewed code.

**Note for mixed Claude/Grok environments:** In Claude Code sessions you may use `/code-review:code-review` (the official plugin) as a fallback, but prefer the Grok bundled reviewer when available for higher-quality structural feedback and proper PENDING review workflow.

### Reflection

After every session completion, you reflect on how the workflow pertaining to the workflow and agent harness - the commands you executed (and which failed consistently), the tools you used, skills invoked, MCP accessed, etc. **Do not include anything feature-specific**. For example, when the Codebase Graph output is too verbose or if certain powershell commands keeps failing. This is not about the features you implemented, but about *how* you implemented them. Write this down in [Insights](docs/insights.md) and then suggest workflow updates to the user in chat.

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
