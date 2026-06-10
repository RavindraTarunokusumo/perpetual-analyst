"""Dossier, observation, and thesis CRUD + memory budget enforcement. See SPEC §8."""

# TODO (Task 2): Implement
# - get_dossier(topic_id, db) -> str | None
# - update_dossier(topic_id, content, db) -> None
#
# - get_observations(topic_id, db, status="active") -> list[Observation]
# - insert_observation(topic_id, obs: NewObservation, db) -> int
# - build_memory_context(topic_id, db, token_budget: int) -> str
#   - importance-sorted, recency-weighted, hard-truncates at token_budget
#   - returns prompt-ready text block
#
# Budget constants:
#   DOSSIER_TOKEN_BUDGET = 1500
#   OBSERVATION_TOKEN_BUDGET = 3000
#
# Invariant: budget truncation is structural (this function truncates),
# NOT behavioral (never ask the model to "write less").
