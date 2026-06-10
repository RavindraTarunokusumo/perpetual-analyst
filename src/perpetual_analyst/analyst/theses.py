"""Thesis lifecycle: create, revise, retire, stale-flagging, audit trail. See SPEC §8."""

# TODO (Task 6): Implement
# - get_active_theses(topic_id, db) -> list[Thesis]
# - apply_thesis_update(update: ThesisUpdate, db) -> None
#   - if update.thesis_id is None: create new thesis (enforce ≤7 active limit)
#   - else: update confidence/status; write thesis_updates audit row
#   - Invariant: theses are NEVER silently edited — always log to thesis_updates
# - get_stale_theses(topic_id, db, days=30) -> list[Thesis]
#   - returns active theses with updated_at older than `days` days
# - render_thesis_fragment(theses, updates) -> str
#   - markdown fragment for "Thesis updates" section with confidence before→after
#
# Hard constraint: raise ValueError if applying an update would result in >7 active theses.
