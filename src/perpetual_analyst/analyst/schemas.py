"""Pydantic output models for the analyst's structured response. See SPEC §7."""

from pydantic import BaseModel, Field


class NewObservation(BaseModel):
    kind: str = Field(description="One of: fact | signal | pattern | contradiction | question")
    content: str = Field(description="The observation text.")
    importance: int = Field(description="1 = minor, 2 = notable, 3 = significant", ge=1, le=3)
    source_item_ids: list[int] = Field(
        default_factory=list,
        description="Item IDs cited as evidence for this observation.",
    )


class ThesisUpdate(BaseModel):
    thesis_id: int | None = Field(
        default=None,
        description="Existing thesis ID to update. None if proposing a new thesis.",
    )
    statement: str = Field(description="Full thesis statement.")
    confidence: float = Field(description="New confidence value, 0–1.", ge=0.0, le=1.0)
    change_rationale: str = Field(
        description="Why confidence changed, or why this new thesis is proposed."
    )
    new_status: str = Field(
        default="active",
        description="One of: active | confirmed | revised | retired",
    )


class TopicAnalysis(BaseModel):
    """Complete output of one analyst run for one topic."""

    report_section_markdown: str = Field(
        description=(
            "The user-facing analysis section for this topic. "
            "Use [item:N] tags for citations. "
            "Empty string if nothing_significant is True."
        )
    )
    new_observations: list[NewObservation] = Field(
        default_factory=list,
        description="New observations to append to the topic's observation log.",
    )
    thesis_updates: list[ThesisUpdate] = Field(
        default_factory=list,
        description=(
            "Thesis changes: updates to existing theses (by ID) "
            "or proposals for new ones (thesis_id=None)."
        ),
    )
    dossier_edits: str | None = Field(
        default=None,
        description=(
            "Full replacement dossier text if it changed. " "None to leave the dossier unchanged."
        ),
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Complete replacement list of open questions for this topic. "
            "Include persisting questions unchanged."
        ),
    )
    watch_next: list[str] = Field(
        default_factory=list,
        description="Sources, developments, or events to monitor next.",
    )
    nothing_significant: bool = Field(
        default=False,
        description=(
            "Set True when today's items contain nothing worth reporting. "
            "Produces a one-line entry in the report. "
            "This is a first-class output — use it when warranted."
        ),
    )
