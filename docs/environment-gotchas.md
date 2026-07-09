# Environment Gotchas

Cross-session environment traps, collected so they aren't re-learned. Add here (not buried in a dated `insights.md` entry) whenever an environment/tooling trap bites a second time.

## Git / worktrees

- **Editable install resolves to the main checkout, not the worktree.** In a git worktree, `import perpetual_analyst` (and therefore `pytest`) loads the main checkout via the shared `.venv` editable `.pth`, so worktree edits appear to have no effect. Run `pip install -e .` from the worktree at session start, or `PYTHONPATH=$PWD/src`; verify `perpetual_analyst.__file__` points inside the worktree. (Also codified in Workflow Step 1.)
- **After deleting a worktree, the shared `.venv` editable install dangles** at the removed path. Reinstall from the active worktree/checkout before running tests.
- **Use merge commits, not squash, for feature PRs.** Squash collapses branch commits to one SHA; archive docs cite per-commit SHAs, which then can't be verified against `git log`.

## Shell (Bash tool)

- **`cd` persists across Bash tool calls** and silently pollutes later commands (a `cd Nexus` changes the repo for everything after). Prefix each command with `cd /abs/path || exit 1`, or use absolute paths throughout.
- **Loading `.env` for scripts that read `os.environ` directly:** `set -a && source .env && set +a` (a plain `source` won't export).

## Python

- **Standalone scripts must not use stdlib module names.** A script's own directory lands on `sys.path[0]` when run directly, so `scripts/inspect.py` shadows stdlib `inspect` and breaks deep imports (e.g. SQLAlchemy). Name scripts distinctively (`pa_inspect.py`).
- **Unterminated module docstring reports at EOF, not the real line.** A missing closing `"""` on line 1 swallows the imports below it; the tokenizer flags the error at the *next* `"""` or EOF. When an error points deep in a file, suspect the line-1 docstring. Enumerate all such errors at once with `python -m compileall src` (now a CI gate).

## `gh` CLI

- `gh pr create` has no `--json`; capture the URL from stdout.
- `gh pr view --json baseRefOid` is unavailable on some `gh` versions; use `headRefOid` + merge-base diff collection.
- Pushing over an HTTPS remote with no credential helper fails ("could not read Username"); run `gh auth setup-git` first (SSH remotes push directly).
- Build any review/API JSON payload with `json.dumps`, never hand-concatenation.

## Auto-mode boundaries

The harness auto-mode classifier denies certain actions regardless of user phrasing — plan the handoff up front rather than discovering it at the moment:

- **An agent cannot merge its own PR** (no self-approval). Hand the merge to the user, or get an explicit permission rule. Never bypass by pushing to `main` directly.
- **Unscoped destructive DB ops are denied** (`TRUNCATE … CASCADE`, unfiltered `DELETE`). Scope cleanup to session-created rows by a known prefix (`WHERE slug LIKE 'scratch-%'`), or run outside auto-mode.

## Platform note

The lessons above are Linux-current. Some historical `insights.md` entries are from a Windows setup (PowerShell here-strings need a column-0 closing `'@`; pre-commit config lives at the repo root, not the worktree CWD). Confirm the platform before applying shell-specific advice.
