# Insights

Record reusable lessons from completed sessions.

## 2026-06-11 — Phase 5 discovery session (workflow/harness)

### What worked well

**The live smoke test (Rule 11) caught a provider-layer bug for the second consecutive feature that touched OpenRouter structured output.** Phase 4 it was nothing; Phase 5 it was the OpenRouter web plugin silently ignoring `response_format=json_object` and prepending prose before the JSON — `model_validate_json(raw)` blew up on the first real call, while all 175 mocked tests passed. Standing rule now: any NEW OpenRouter call shape (a new plugin, web search, a new param) must get a live smoke test before PR, and structured-output parsing should be tolerant (extract the JSON object substring) rather than assuming `json_object` is honored. Mocks validate wiring; only a live call validates the provider contract.

**Recovering a subagent interrupted mid-task without losing or duplicating work.** The Task D implementer hit the session limit after 17 tool uses and returned an empty result — its four files were written but uncommitted. The right move was NOT to re-dispatch (which would redo/duplicate): per Workflow Rule 8, run `git status` first, read the uncommitted files, run the suite + pre-commit, verify the work against the task spec, then commit it myself on the agent's behalf. Re-dispatching a "finished but uncommitted" task is the trap to avoid.

**Reinstalling the editable package at session start (Phase 4 insight) paid off.** Starting Phase 5 from a fresh worktree, `pip install -e .` re-pointed the shared `.venv` immediately; the baseline suite ran green on the first try. The habit works.

### What to improve

**The GitNexus stale-index hook fired on every single Bash command for two full sessions and never self-resolved.** It is pure noise once acknowledged, and the index (pinned at the Phase 1 commit) is useless for impact analysis on a branch that is now four phases ahead — so the CLAUDE.md "MUST run gitnexus_impact before editing" step is unfollowable as written. Either re-run `npx gitnexus analyze` once at the start of a multi-phase effort, or relax the hook/rule when the index predates the working branch's base. Acting on a four-phases-stale graph would be worse than reading callers directly.

**`/simplify` keeps surfacing out-of-scope or behavior-changing suggestions that must be filtered, not applied.** This phase: a `thinking_extra` helper that would edit Phase 1–4 call sites (out of scope), module relocations (larger restructure), and the "two sources of truth" framing of an additive migration (which is actually the correct pattern). The discipline: apply only behavior-preserving, in-scope cleanups; note the rest with a one-line reason rather than letting the cleanup pass balloon the diff right before PR.

### Patterns established this session

- New OpenRouter call shapes get a live smoke test before PR; parse structured output tolerantly (don't trust `response_format=json_object` across plugins/providers).
- Subagent interrupted mid-task → verify the working tree and commit its work yourself; don't re-dispatch.
- When GitNexus is indexed older than the working branch's base, skip the impact step and read callers directly — say so explicitly.

## 2026-06-11 — Phase 4 compaction session (workflow/harness)

### What worked well

**Front-loading project gotchas into each subagent prompt eliminated rework.** Five implementer subagents (Sonnet) shipped clean, green commits with zero correction loops because each prompt embedded the project-specific traps verbatim: the portable `create()` + `model_validate_json()` pattern (not `.beta.parse()`), "no `ge`/`le` on numeric Pydantic fields," the PowerShell single-quoted here-string rule for commit messages, and "run pre-commit only on your touched files." When the controller curates these upfront, the implementer doesn't rediscover them.

**A whole-branch final review caught a cross-task gap the per-task reviews could not.** Each task passed its own review, but only the final reviewer over the full diff spotted that the weekly path rebuilt the daily message shape without the cache breakpoint — an inconsistency that's invisible when reviewing tasks in isolation. The final-review step in subagent-driven-development earns its keep specifically for cross-cutting consistency.

**Gating outward-facing spend with a single question fit auto mode.** The live API smoke test and the PR merge were both real, hard-to-reverse actions; one `AskUserQuestion` each kept momentum while leaving the cost/irreversibility decisions with the user.

### What to improve

**After deleting a worktree, the shared `.venv` editable install is left dangling.** The root `.venv` had `pip install -e .` pointed at the *previous* (now-deleted) worktree, so pytest failed with `ModuleNotFoundError: perpetual_analyst` until I re-ran `pip install -e .` from the new worktree. Rule: the Preamble (Step 1) for any session that uses a fresh worktree should reinstall the editable package from that worktree before running tests.

**`/simplify` can propose behavior-changing "simplifications" — verify before applying.** One cleanup agent suggested collapsing the `render_thesis_trail` start/end search into a single pass, but the proposed form changed the semantics (per-row `confidence_before`/`after` mixing instead of "earliest non-null before across all rows"). Treat `/simplify` findings as candidates: confirm behavior-preservation against the original logic before editing, and skip the ones that don't hold.

**GitNexus was indexed against `main` (Phase 1) the entire session, making impact analysis useless on the feature branch.** The index predated Phase 2/3/4 symbols, so `gitnexus_impact` on `assemble_context`/`run_topic` would have returned a stale, misleading blast radius. I verified callers by reading files directly and noted the staleness instead. Also, the `PostToolUse` hook reprinted "GitNexus index is stale" on *every* Bash call — pure noise once acknowledged. When the index is older than the working branch's base, skip the GitNexus MUST-DO impact step and say so; don't act on a stale graph.

### Patterns established this session

- Reinstall the editable package (`pip install -e .`) from the new worktree at session start — the shared `.venv` may point at a deleted one.
- Curate project-specific gotchas into subagent prompts; don't rely on the implementer to rediscover them.
- Keep a final whole-branch review even when every task was individually reviewed — it catches cross-task drift.
- Validate `/simplify` suggestions for behavior-preservation before applying.

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
