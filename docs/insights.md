# Insights

Record reusable lessons from completed sessions.

## 2026-06-10 — Phase 1 implementation session

### What worked well

**Subagent-driven development with task isolation:** Dispatching a fresh Sonnet subagent per task kept each agent's context clean and made reviews reliable. The spec reviewer and code quality reviewer catching genuine issues (dedupe invariant, thesis status gap, path traversal) justified the overhead.

**Two-model review pattern:** Sonnet for spec compliance, Opus for code quality and security — this split worked well. Opus consistently caught the non-obvious invariant gaps that Sonnet spec-review missed (unbounded context budget, `make_client` dead code). Using it as a substitute for Copilot Code Review was effective.

**Writing failing tests first:** The TDD step where subagents ran failing tests before implementing made it obvious when imports were broken early, not after 50 lines of implementation.

**`executescript()` for FTS triggers:** The key fix was that SQLite `CREATE TRIGGER ... BEGIN ... END` blocks contain internal semicolons that break naive `;` splitting. Using `executescript()` was the correct fix; preserving this in the git note and plan document means future sessions won't rediscover it.

### What to improve

**`/simplify` skill is not installed.** The Pre-PR workflow calls `/simplify` but it doesn't exist in the plugin. The closest available skill is `/code-review` with `--fix`. Update `CLAUDE.md` to use `/code-review ultra` or `/simplify` only when it's available.

**PowerShell here-strings require column-0 closing `'@`.** Bash-style `$(cat <<'EOF'...)` commits fail silently in the Bash tool on Windows; PowerShell `@'...'@` works but the closing marker must be at column 0. Any subagent writing commit messages needs this in the prompt or they use the wrong syntax.

**Pre-commit hook absent from worktree CWD.** When subagents run pre-commit from inside `.worktree/`, the `.pre-commit-config.yaml` is at the repo root, not the worktree directory. The fix is to always run pre-commit with the full path (`C:\...\root\.venv\Scripts\pre-commit run --all-files`) from the **root** directory, not the worktree CWD. Or set `PRE_COMMIT_ALLOW_NO_CONFIG=1` when running from the worktree.

**Squash-merge loses per-commit SHAs for archive tagging.** With squash-merge, all branch commits collapse to a single merge SHA. The archive sub-item hashes were recorded from branch history, but future readers can't verify them against `git log`. Consider using merge commits (`--no-squash`) for easier archive tracing, or document that branch SHAs are pre-squash only.

**Dead monkeypatch in conftest.** When `run_topic` takes `client` directly as a parameter, patching `make_client` is a no-op. Future sessions should check whether the production call path actually invokes the patched function before adding a monkeypatch.

**Context compaction timing:** The session crossed a context window boundary mid-planning (after brainstorming, before writing the plan). After compaction, `git status` was the correct first action (per Workflow Rule 8), but the compacted summary said "intent, not state" — always verify against actual git state before touching files.

### Patterns established this session

- `insert_item(conn, ...) -> bool` is the only safe item write path — callers must never use plain `INSERT INTO items`
- `apply_all_memory_writes` owns the transaction; individual CRUD functions don't call `conn.commit()`
- `assemble_context` is stateless (reads only); all writes go through `apply_all_memory_writes`

## 2026-06-10 — Project onboarding

- What worked: Generating complete harness (AGENTS.md, docs/, .codex/, .github/) from SPEC.md in one session before any implementation. Gives agents a navigable skeleton.
- Key design decisions preserved in docs: memory tiers are in `docs/database.md`; anti-patterns are in `docs/patterns.md`; context assembly order is in `docs/architecture.md`.
- Workflow improvement: Start Phase 1 with `analyst run --dry-run` to verify context assembly before making real API calls.
- Skill worth adding: A `perpetual-analyst-analyst-tuning` skill for iterating on `analyst/prompts/analyst_system.md` based on report quality feedback.
