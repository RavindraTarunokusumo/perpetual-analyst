# Insights

Record reusable lessons from completed sessions.

## 2026-06-14 — Web UI dashboard session

### What worked well

**The `pip install -e .` Preamble step (added this session) removed real friction.** Every implementer and the live-validation step imported the package and ran `pytest`/`analyst web` with no `PYTHONPATH` dance. The console script (`analyst.exe`) re-pointed at the worktree's `src/` after the editable install, so live-validating the *worktree* code Just Worked. Worth keeping as a hard Preamble step.

**Cost-tuned the subagent-driven loop without losing rigor.** Instead of the skill's 2 review subagents per task (≈20 dispatches), I verified spec-compliance *inline* by reading each committed diff (cheap; I authored the plan) and ran **consolidated Sonnet code-quality reviews at group boundaries** (read-pages, then actions) plus **one final whole-branch review** — far fewer dispatches, and it still caught real bugs at every stage (thesis slug/topic 404, run-lock deadlock window, CSRF, a test that passed via the wrong code path). When the plan is fully prescribed and you authored it, inline spec-checking + grouped quality reviews is a good cost/quality trade.

**The final whole-branch review earns its place even after per-group reviews.** Group reviews see code in isolation; the whole-branch pass caught *cross-cutting* defects the group passes structurally couldn't — most valuably a test that returned 302 via the unconfigured fast-path and never exercised the function it monkeypatched (a false-green). Always run the final pass; treat "a test that would pass even if the code were broken" as a first-class finding.

### What to improve

**A review subagent silently hit a stream-idle-timeout (~31 min, zero output).** The actions-group reviewer never returned. Inline fallback worked (I did the review myself and found the lock-release deadlock). Lesson: the inline-fallback rule isn't only for session-limit errors — a long review/analysis subagent can time out with nothing; when it does, review inline rather than re-dispatching and waiting again.

**The visual-companion server idle-timed-out (30 min) during a long stretch of terminal Q&A.** I started it at the top of brainstorming, then spent many turns on *conceptual* (terminal) questions, so no screen was pushed and it self-exited; I had to restart it right before the first mockup. Lesson: start the companion **immediately before pushing the first visual**, not when the user first accepts it — and push a screen promptly to reset the idle timer.

**`doc-updater` invented a version label.** It titled the changelog entry "Phase 4: …" although Phase 4 is reserved (weekly compaction); the feature was out-of-SPEC. Caught and fixed. Lesson: review doc-updater output for invented phase/version naming, not just content accuracy.

**`ruff-format` reformats multi-line SQL strings on every commit.** Each implementer wrote `conn.execute("..." "...")` split strings and ruff collapsed/implicit-joined them on the pre-commit hook, forcing a re-stage + re-commit. Minor but recurring across all ~13 task commits. Pre-empt by writing SQL in ruff's preferred single-line/implicit-concat form, or run `ruff format` before staging so the first commit is clean.

**Workflow Rule 11 (file-based bodies) held up.** PR body written with the Write tool → `gh pr create --body-file` as its own command → no silent failure (the Phase-3 chained-heredoc breakage did not recur). The `git commit -F - <<'MSGEOF'` heredoc form also worked reliably for multi-line commit messages in the Bash tool.

## 2026-06-13 — Phase 3 implementation session

### What worked well

**Two-stage substitute review when Copilot is down (whole-branch, then fix-commit).** The pre-PR whole-branch Opus review found the empty-items double-call bug; after fixing it, a SECOND focused Opus review of only the fix commits caught that one of those fixes (`_balance_html`) had introduced a silent-data-loss regression. Lesson: fixes made in response to a review are themselves unreviewed code — run a focused pass over the fix delta, not just the original branch. The implementer's self-review is not a substitute.

**Live `--dry-run` as a plan task caught a class of bug mocks never will.** The dry-run (real feed fetch, zero API calls) surfaced a Windows cp1252 `UnicodeEncodeError` on piped stdout — invisible to the test suite (pytest captures differently) and to interactive runs (console is UTF-8). Any CLI that prints unicode needs `sys.stdout.reconfigure(encoding="utf-8")` at the entry point for scheduled/piped execution.

**Bounded the slow live validation instead of skipping it.** The first dry-run subagent timed out at 14 min on arXiv's full first-fetch and reported DONE_WITH_CONCERNS without completing the validation. The fix was a 6-line prep script marking the heavy feeds `last_fetched_at = now` so the dry-run exercised the full pipeline on a small feed in seconds. When a validation is too slow, shrink its input rather than declaring it unverifiable.

### What to improve

**PowerShell here-string piped to `gh ... --body-file` then `Remove-Item` failed as one compound command.** The `@'...'@ | Out-File ...; gh pr create ...; Remove-Item ...` chain errored (Remove-Item resolved oddly) and the PR was NOT created. Write PR/comment bodies with the Write tool to a file, then run `gh` as its own command, then clean up separately — don't chain heredoc + gh + delete.

**`git checkout main` fails from inside a worktree** (main is checked out in the primary dir). For post-PR work on main, operate in the primary working directory with `git -C <main-path> ...` rather than trying to switch the worktree to main. Pull main with `git -C <main> pull --ff-only origin main`.

**Subagents repeatedly hit the GitNexus stale-index warning** but correctly did not run `npx gitnexus analyze` (the worktree-rewrites-AGENTS/CLAUDE.md hazard from Phase 2). Keep telling subagents NOT to reindex in a worktree; the stale warning is harmless when impact analysis is run from the primary dir or skipped for LOW-risk leaf additions.

### Patterns established this session

- A review that produces fixes must be followed by a review OF those fixes (fix-delta review)
- CLI entry points that print unicode must force UTF-8 stdout for piped/scheduled use
- Telegram (and any `parse_mode=HTML` sink) requires escaping stray `<`/`>`/`&` while preserving the allowlisted tags — never a regex strip that can eat literal `<`
- Slow live validations get a bounded-input harness, not a skip

## 2026-06-12 — Phase 2 implementation session

### What worked well

**Live smoke testing as a first-class plan task.** Two latent Phase 1 bugs (provider rejecting `minimum`/`maximum` in structured-output schemas; `response.parsed` not existing on the real SDK object) were invisible to a 100-test mocked suite and surfaced only on a real API call. Mocks that fabricate the response shape validate the mock, not the contract — when correcting such a bug, fix the conftest mock in the same commit so the suite pins the real shape.

**Empirical verification before applying review findings.** Three reviewer claims were rejected with reproductions (a `time.strftime` timezone claim disproven with a 5-line script; a "double period" formatting claim disproven by an exact-line assertion; a ×0.5-vs-×1.5 boost direction confirmed against bm25 sign semantics). Each rejection was cheaper than the wrong "fix."

**Plan-with-complete-code + Sonnet implementers.** Prescribing full test/implementation code in the plan made per-task subagents fast and reviewable. Implementers caught two genuine plan bugs by running the tests (`NOT IN (NULL)` three-valued-logic row-drop; a test fixture producing identical content hashes that dedupe collapsed) — evidence the TDD steps protect against the planner too.

**Substitute Opus PR review when Copilot is down.** The Opus reviewer reproduced (not speculated) two real bugs the suite couldn't see: a hallucinated `thesis_id` FK-aborting the whole memory transaction, and triage demoting `analyzed` items. Reproduce-before-report should be the bar for all review subagents.

### What to improve

**Long-running commands die with the dispatching subagent.** A 40-minute live pytest launched in a subagent's foreground shell was killed when the subagent's turn ended (the run survived to feed-fetch only). Long-running verification must be launched by the orchestrator with `run_in_background` (log to a file with an appended `EXIT: $LASTEXITCODE` marker), never inside a subagent.

**Subagents hit the Claude session limit mid-workflow.** Four parallel /simplify reviewers all died instantly on a session limit; the inline fallback (doing the 4-angle review in the main context) worked fine. When dispatches start failing with limit errors, switch to inline rather than retrying.

**`npx gitnexus analyze` inside a worktree rewrites AGENTS.md/CLAUDE.md.** A subagent's reindex registered the worktree as a separate repo ("phase-2") and rewrote the GitNexus block in both files. Tell subagents not to run gitnexus analyze in worktrees; keep the dirtied files unstaged (specific staging protected every commit).

**OpenRouter 402 on max_tokens reservation.** The analyst call reserves ~65K output tokens; a smoke run fails with 402 if the account balance can't cover the reservation even when actual usage would be far less. Check credit headroom before scheduling live runs.

**Serial trafilatura extraction dominates smoke wall time.** ~40 minutes for 363 arXiv entries (per-article page fetches). For Phase 3+: consider a first-fetch entry cap or concurrent extraction before scaling topics.

**`gh pr merge` + local unpushed state.** Local main carried an unpushed commit that reached origin only via the PR branch; the post-merge `git pull` then collided with pre-existing dirty test files (stash, pull, proceed). Check `git status` in the MAIN working dir before merging, not just the worktree.

### Patterns established this session

- Provider-bound Pydantic models must not carry `ge`/`le` (serialize to rejected `minimum`/`maximum`) — use clamping `field_validator`s
- bm25 scores are negative: recency boosts multiply by >1, never <1
- `sync_config` owns topic/source definitions (YAML → DB); runtime columns are DB-only; inbox sources exempt from deactivation
- Item status transitions are guarded: triage writes only `status='new'` rows; analyzed-marking lives inside `apply_all_memory_writes`
- LLM-provided IDs (item_id, thesis_id) are validated against known sets before any DB write

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
