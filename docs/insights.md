# Insights

Record reusable lessons from completed sessions.

## 2026-06-10 — Project onboarding

- What worked: Generating complete harness (AGENTS.md, docs/, .codex/, .github/) from SPEC.md in one session before any implementation. Gives agents a navigable skeleton.
- Key design decisions preserved in docs: memory tiers are in `docs/database.md`; anti-patterns are in `docs/patterns.md`; context assembly order is in `docs/architecture.md`.
- Workflow improvement: Start Phase 1 with `analyst run --dry-run` to verify context assembly before making real API calls.
- Skill worth adding: A `perpetual-analyst-analyst-tuning` skill for iterating on `analyst/prompts/analyst_system.md` based on report quality feedback.
