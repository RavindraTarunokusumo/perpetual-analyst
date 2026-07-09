# 2026-07-09 — Workflow hardening (CI gate + rules from recurring insights)

**Spec:** none (process/harness change derived from a review of `docs/insights.md`, requested in-session).

**PR:** #12 · **Merge commit:** `79ed66e`

## What shipped

Turned recurring, previously-advisory `insights.md` lessons into enforced mechanisms, and added the CI gate that was missing.

- [x] **CI merge gate** — `.github/workflows/ci.yml`: `ruff check` + `ruff format --check` + `compileall` on `src`, on every PR and push to `main`. `compileall` alone would have blocked the four SyntaxErrors that reached `main` this week — `d263d85`
- [x] **`src` ruff-cleaned** so the gate is green: mechanical autofix (UP017, unused import) + `ruff format`, plus a real latent bug — missing `import sqlite3` in `config.py` (F821, masked by lazy annotations) — `2cbd096`
- [x] **pre-commit ruff pinned** `v0.5.0`→`v0.15.20` to match the local/CI ruff so the hook and CI can't disagree on format — `d263d85`
- [x] **CLAUDE.md / AGENTS.md rules** (kept in sync): Preamble worktree editable-install step; GitNexus stale-index fallback; Rules 13–16 (merge-commit-not-squash, auto-mode boundaries, live-smoke-before-PR, never-merge-red-CI); Pre-Commit cleanup-as-candidates note; Reflection "promote a 2nd-occurrence lesson into an enforced mechanism" — `d470cb1`
- [x] **`docs/environment-gotchas.md`** — collected one-offs (cd persistence, stdlib script shadowing, gh quirks incl. the `workflow` token scope, auto-mode denials) — `d470cb1` / `15a15a1`

## Validation
- CI gate commands green locally; `ci.yml` valid YAML; pre-commit passes with the new ruff pin.
- **CI verified executing on GitHub Actions** — ran green on PR #12 (same-repo PRs run the workflow from the head branch) *and* on `main` post-merge (`push`).
- `src` cleanup diff confirmed mechanical (autofix + format + one import); no behavior change.

## Notes / discovered gotchas (now in `docs/environment-gotchas.md`)
- Pushing a `.github/workflows/*` file needs the `gh` `workflow` token scope (`gh auth refresh -s workflow`); the whole branch push is blocked until granted.
- CI *does* run on the PR that introduces the workflow (same-repo) — verify empirically, don't assume it won't.

## Backlog unchanged
Test suite still does not collect on `main`; stale dashboard-port doc — both in `TODO.md`. CI's `pytest` gate and widened ruff scope (`.`) are the follow-up once the suite is repaired.
