# Insights

Record reusable lessons from completed sessions.

## 2026-07-09 — Web UI refresh (Grok-delegated, 7-task session)

### Workflow / harness lessons

**A 6-task feature fits cleanly into 6 sequential Grok handoffs when each prompt is fully self-contained.** Every handoff embedded the exact file scope, exact CSS token values / SQL shape / helper signature, the validation commands to run, and the "final report" format to return. Zero correction loops across 7 handoffs (6 tasks + 1 fix batch) — the cost of writing a precise prompt was paid once and saved a full review-reject-redo cycle every time.

**Deleted test fixtures are often recoverable from git history, not just rewritable from scratch.** The web test suite's `client`/`seeded_conn`/`db_path` fixtures were silently dropped in a later refactor. `git show <commit>:tests/conftest.py` on the commit that first added them (found via `git log -S "def db_path"`) recovered the original block verbatim; the Grok handoff only had to adapt it to schema drift (`init_db` now pre-seeds user id 1, so the seed's `INSERT` needed `OR REPLACE`). Cheaper and more faithful than reinventing fixture semantics from the failing tests alone.

**Grok's own trailing-newline discipline is inconsistent — check every diff for `\ No newline at end of file`.** Despite explicit prompt instructions ("files end with exactly one trailing newline") in every task, 3 of 6 handoffs (T4, T5, T6) still stripped the final newline on template files. `git diff --check` catches it immediately; fix with one `printf '\n' >>` before validating and committing. Don't rely on the instruction alone — verify.

**A Grok session sometimes "simulates" the implementation via internal reasoning rather than actually invoking file-edit tools, but still produces a correct diff.** The T2 (CSS) session's `thought` trace showed it reasoning through what the file *should* contain rather than narrating tool calls — worth noting only because it means the "final report" prose can't always be trusted as evidence of what happened; the git diff is the only ground truth. Always diff-review before trusting a Grok "complete" report, regardless of how confident the prose reads.

**Cross-file consistency bugs (the kind a single-task review can't see) are exactly what a whole-branch review catches.** The Grok branch review caught two real inconsistencies invisible to any individual task's own tests: `topic_list.updates_today` didn't filter by thesis status while `today_changes` did (T6 vs. T4 drift), and confidence-series extraction was duplicated between `confidence_points` and the thesis route (T5) with no shared source of truth. Per-task validation was green throughout; only the full-diff pass surfaced the drift. Confirms the Phase-4 lesson: a whole-branch review earns its keep even when every task passed individually.

**Not every review finding is a bug — triage explicitly, and record the "no" with a reason.** Of 8 branch-review findings, 3 were declined (a UI limitation with no cheap fix in scope, an intentional date-basis difference, a low-value edge case) and recorded with technical reasoning in `session_ledger.json` rather than silently dropped or blindly applied. The `receiving-code-review` skill's verify-before-implementing stance applies to agent-generated review findings exactly as much as to a human reviewer's.

**A live-rendered-page visual artifact (not screenshots) is a fast, faithful way to sanity-check both themes before merge.** Serving `create_app` on a seeded temp DB, curl-fetching each real route, and embedding the actual HTML (CSS inlined, script tags stripped) into light/dark iframes in one Artifact caught nothing wrong here but would have caught a dark-mode token miss immediately — cheaper than spinning up a real browser, and it's the true rendered output, not a description of it.

### Patterns established this session

- Grok task prompts for this repo should always specify: exact file scope (with an explicit "touch nothing else"), exact values/shapes for anything visual or structural (don't leave palette/geometry to the implementer's judgment), the literal validation commands, and the final-report shape.
- After every Grok handoff: `git diff --check` (trailing newline), diff read (don't trust the prose report), targeted pytest + ruff, then commit — in that order, every time, no batching multiple tasks before review.
- Session ledger `handoffs` list should record `sessionId` + result + cleanup status per task as it happens, not reconstructed at wrap-up — made the archive doc trivial to write.

## 2026-07-09 — Workflow hardening (CI gate + rule promotion)

### Workflow / harness lessons

**Close the reflection loop: promote a 2nd-occurrence lesson into an enforced mechanism, same session.** This session was that rule applied — three lessons that had recurred 3–4× as advice (editable-install-in-worktree, GitNexus stale index, `/simplify` scope) became a Preamble step, a GitNexus fallback rule, and a Pre-Commit note; plus CI. The reflection step now mandates this (CLAUDE.md), so recurring traps stop being re-learned. Advisory prose in `insights.md` is where lessons go to be forgotten.

**Bootstrap CI on a debt-laden repo by gating only what's green today.** The suite doesn't collect and even `src` wasn't lint-clean, so a full `ruff .`/`pytest` gate would have been born red. Scope the gate to what passes now (`compileall` + `ruff` on `src`) — `compileall` alone catches the actual regression class (the four committed SyntaxErrors) — and document the rest (pytest, `ruff .`) as a tracked follow-up to widen once the debt clears. A narrow green gate beats a broad red one nobody can satisfy.

**Verify CI executes; don't reason about whether it will.** I predicted CI wouldn't run on the PR that introduces the workflow — wrong: for same-repo PRs GitHub runs `ci.yml` from the head branch, so it ran green on the PR *and* on `main` post-merge. `gh run watch --exit-status` confirmed it. Check the run, don't theorize about triggers.

**Pin pre-commit and CI to the same tool version.** Local ruff was `0.15.20`; pre-commit pinned `v0.5.0` — a format-output gap that lets a commit pass the hook and fail CI. Bumped both to `v0.15.20` (verify the `ruff-pre-commit` tag resolves by running the hook once). Any formatter/linter that gates in two places must be one version.

**Adding a `.github/workflows/*` file needs the `gh` `workflow` token scope.** Push is rejected ("refusing to allow an OAuth App to … workflow … without `workflow` scope") until `gh auth refresh -s workflow`; the whole branch is blocked, not just that file. (Now in `docs/environment-gotchas.md`.)

## 2026-07-09 — Web UI polish + run-blocker fixes (worktree session)

### Workflow / harness lessons

**Compile-scan the whole package before fixing syntax errors one at a time.** A "small CSS polish" surfaced a chain of committed syntax/import errors. Fixing them by re-running imports was whack-a-mole (triage → cli → …). `python -c "import ast,pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('src').rglob('*.py')]"` enumerates every `SyntaxError` in one pass — do this first when one broken import appears.

**Unterminated module docstring reports at EOF, not the real line.** A missing closing `"""` on line 1 swallows the imports below it; the tokenizer flags "unterminated string literal" at the *next* `"""` or EOF, far from the cause. When an error points deep in a file but the module's line-1 docstring looks off, suspect the docstring.

**Editable installs resolve to the main repo `src`, not the worktree.** In a git worktree, `import perpetual_analyst` (and therefore `pytest`) silently loads the main checkout via the editable `.pth`, so worktree edits appear to have no effect. Set `PYTHONPATH=<worktree>/src` (and assert `module.__file__` starts with it) to actually exercise worktree code.

**Verify UI by driving it, not by reading templates.** Flask `test_client` against a seeded temp DB caught nothing wrong here, but *proved* every route renders 200 through the real import chain; a live `serve_dashboard` + `curl` smoke confirmed the actual entry point. When the app can't be launched at all (blockers), rendering the real pages into iframes with CSS inlined makes a faithful visual Artifact stand-in.

**Separate "blockers to the goal" from "unrelated refactor rot," and get a scope decision before crossing that line.** The task exposed a half-finished migration (removed modules, drifted APIs, a non-collecting test suite). Fixing the UM-import/run blockers was in scope; rewriting the test suite was not. Pausing with an `AskUserQuestion` to pick the scope boundary — and logging the rest as backlog — kept the session bounded instead of sprawling into someone else's abandoned refactor.

**Auto-mode blocks an agent self-merging its own PR even when the user says "you merge it."** The classifier denied `gh pr merge` on an agent-authored PR (no human review / self-approval). Expect to hand the merge to the user or get an explicit permission rule; don't work around it by pushing to `main` directly (that bypasses the review the block protects).

## 2026-07-08 — Firecrawl source extraction (worktree session)

### Workflow / harness lessons

**Pre-PR `/review` is not optional even when the diff looks clean.** The first attempt used a non-existent `code-reviewer` subagent and fell through to a quick self-read before opening the PR. Running `/review` post-open caught two real RSS-semantics bugs (narrow `ArticleFetchError` catch + unguarded Firecrawl response parsing). Treat review failure or skip as a blocker before merge, not a nice-to-have.

**GitHub PENDING reviews via `gh api`.** `gh pr view --json baseRefOid` is not available on this `gh` version; use `headRefOid` plus merge-base diff collection. Build the review payload with `json.dumps` (never hand-concatenate JSON). Post with `gh api repos/{owner}/{repo}/pulls/{n}/reviews` omitting `event` for PENDING state; user submits from the PR Files tab.

**Carry WIP into the worktree via stash, not parallel edits on `main`.** Stashing uncommitted extraction work, creating `.worktree/firecrawl-source-extraction`, and `stash pop` left `main` clean while preserving in-flight commits — the right preamble when a feature starts mid-session on dirty `main`.

**Live provider smoke after unit tests.** Mocked tests passed bot-wall detection, but only `pytest -m smoke` with real `FIRECRAWL_API_KEY` confirmed Reuters extraction (~10k chars, ~1.7s). Load `.env` with `set -a && source .env && set +a` because smoke tests read `os.environ` directly (no `load_dotenv` in the test module).

**Defense in depth for item-level RSS semantics.** Spec promises summary fallback without `fetch_error_count` bumps. Fixing both `rss._extract_text` (broad `except Exception`) and `extract_url` (wrap unexpected failures in `ArticleFetchError`) plus regression tests on `fetch_error_count` is safer than relying on a single catch type.

## 2026-07-08 — PA ↔ Nexus integration (multi-repo, Grok-delegated)

### Workflow / harness lessons

**`cd` persists across Bash tool calls — it pollutes later commands.** A `cd Nexus` in one call silently changed the repo for subsequent calls, producing wrong-repo results. Prefix every command with `cd /abs/repo/path || exit 1`, or use absolute paths throughout. Never rely on inherited cwd.

**The auto-mode classifier blocks destructive DB operations — scope them.** `TRUNCATE … CASCADE` and an unfiltered `DELETE FROM <table>` (even off an unfiltered `SELECT … FROM watch_topics`) were denied because they could wipe real data. Scope cleanup to session-created rows by a known slug prefix (`WHERE slug LIKE 'scratch-%'`); expect broad destructive DB cleanup to need explicit filters or to run outside auto-mode.

**Standalone scripts must not use stdlib module names.** A helper at `scripts/inspect.py` shadowed the stdlib `inspect` module (its dir lands on `sys.path[0]` when run directly), breaking `typing_extensions` deep inside SQLAlchemy import. Name scripts distinctively (`pa_inspect.py`).

**`gh` gotchas.** `gh pr create` has no `--json`; capture the URL from stdout. Pushing over an HTTPS remote with no credential helper fails ("could not read Username"); run `gh auth setup-git` first (SSH remotes push directly).

**Multi-repo submodule finalization order.** Merge the upstream repo's PR first, bump the submodule to the *merge commit* (not the branch tip — a squash could orphan the pinned SHA), then merge the dependent PR. Use a merge commit (not squash) so per-commit SHAs survive for archive tracing.

**Grok delegation.** Grok sometimes runs a task "inline" and reports `sessionId: N/A` in prose — still parse the JSON `sessionId` and clean up the CLI session dir. It correctly *declined* to edit a test outside its stated file scope and flagged it instead (good boundary discipline; the senior applies the out-of-scope test fix during review). It also strips trailing newlines and can quietly change unrelated `pyproject` pins — normalize newlines and diff `pyproject` for scope creep before committing.

**Live e2e with the real provider beats unit tests for behavior/estimates.** A degenerate test doc (one sentence repeated) produced 1 claim and a misleading cost estimate; realistic input produced 7 claims. Always validate model-facing behavior and cost/latency numbers with realistic inputs, not synthetic filler.

## 2026-07-08 — Harness workflow blocker session

### What worked well

**Recording environment blockers in `session_ledger.json` kept the workflow auditable even when the normal git path was unavailable.** Capturing the exact commands and failures made it clear which workflow steps were completed, which were best-effort, and which were blocked by filesystem or dependency constraints.

**A dependency-free syntax and smoke-test fallback provided useful validation when pytest/ruff/pre-commit could not be installed.** `compileall`, `git diff --check`, line-length scans, and small `PYTHONPATH=src` smoke scripts are not substitutes for the full suite, but they are worth running when package installation is blocked.

### What to improve

**The sandbox exposed `.git` as read-only, which blocks worktree setup, staging, commits, git notes, and PR submission.** A session that requires the full workflow needs writable git metadata; otherwise the implementation can be prepared but cannot satisfy the commit/PR/archive portions of the harness.

**GitNexus MCP did not expose `perpetual-analyst` even though the repo contract says it should.** Impact and detect-changes calls failed with only `Indonesia-Monitor` and `Nexus` available. Future sessions should check `mcp__gitnexus.list_repos` early and record a fallback when the expected repo is missing.

**Grok CLI availability is not enough; it also needs a writable session store.** The CLI was installed, but non-interactive JSON handoff failed because session creation hit a read-only filesystem. The harness should treat "Grok installed but cannot create a session" as a first-class fallback condition.

### Patterns established this session

- If `.venv` is absent, create it, but record dependency installation failures explicitly when network access blocks `pip install -e ".[dev]"`.
- When pytest is unavailable, still run `compileall`, `git diff --check`, and targeted `PYTHONPATH=src` smoke checks.
- If `.codex/` is read-only, update writable docs and record the remaining harness-prompt drift rather than silently skipping it.

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
