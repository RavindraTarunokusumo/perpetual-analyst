## Summary

- What changed and why?
- Keep this focused on behavior and outcomes.

## Root Cause (for fixes)

- What was broken?
- Why did it happen?
- If not a bug fix, write `N/A`.

## Scope of Changes

| Area | Description |
|------|-------------|
| Analyst / Memory | |
| Ingestion | |
| Retrieval | |
| Store / DB | |
| Report / Delivery | |
| Docs | |
| Tests | |

## Test Plan

- [ ] `ruff check . --fix && ruff format .` passed
- [ ] `pytest` passed
- [ ] Dry-run validated (`analyst run --dry-run`) if analyst behavior changed
- [ ] Memory writes verified in DB if memory module changed
- [ ] Manual validation completed (describe below)

Manual validation notes:

## Risk and Rollback

- Risk level: `low` / `medium` / `high`
- Main risk areas:
- Rollback plan:

## Docs and Backlog

- [ ] Updated `docs/architecture.md` if module boundaries or data flow changed
- [ ] Updated `docs/database.md` if schema changed
- [ ] Updated `docs/patterns.md` if new patterns emerged
- [ ] Updated `docs/changelog.md`
- [ ] Updated `TODO.md` / moved completed items to `docs/iterations/archive/`
- [ ] Added git notes per commit using `.github/git_notes_template.md`

## Invariants Checked

- [ ] One analyst call per topic per day (no new model call loops added)
- [ ] Memory writes are transactional
- [ ] Theses are not silently edited (audit trail present)
- [ ] `nothing_significant` path works end-to-end
- [ ] No secrets logged

## Related

- Issue(s):
- TODO/Iteration item:
- PR type: `feat` / `fix` / `chore` / `docs` / `refactor` / `test`
