"""Typed row models for each DB table. See SPEC §5 for field descriptions."""

# TODO (Task 1): Implement
# Use dataclasses or Pydantic models (prefer dataclasses for pure DB rows).
#
# Models needed (one per table):
#   User, Topic, Source, TopicSource, Item, Chunk,
#   Dossier, Thesis, ThesisUpdate, Observation, Report
#
# Example pattern:
#   @dataclass
#   class Topic:
#       id: int
#       user_id: int
#       slug: str
#       name: str
#       brief: str | None
#       active: bool
#       created_at: str
