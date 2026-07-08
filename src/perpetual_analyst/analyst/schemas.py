"""Pydantic output models for the analyst's structured response. See SPEC §7."""

from pydantic import BaseModel, Field


class NewObservation(BaseModel):
    kind: str = Field(description="One of: fact | signal | pattern | contradiction | question")
    content: str = Field(description="The observation text.")
    importance: int = Field(description="1 = minor, 2 = notable, 3 = significant")
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
    confidence: float = Field(description="New confidence value, 0–1.")
    change_rationale: str = Field(
        description="Why confidence changed, or why this new thesis is proposed."
    )
    new_status: str = Field(
        default="active",
        description="One of: active | confirmed | revised | retired",
    )


class SourceProfileOut(BaseModel):
    source_type: str = Field(description="Source category, e.g. news, blog, research.")
    incentive_note: str = Field(description="Brief note on the source's incentives or bias.")
    reliability: float = Field(description="Estimated source reliability, 0–1.")


class ClaimOut(BaseModel):
    claim_text: str = Field(description="Atomic source-backed assertion.")
    entities: list[str] = Field(
        default_factory=list,
        description="Named entities mentioned (orgs, people, models).",
    )
    confidence: float = Field(description="Confidence in the claim, 0–1.")
    source_authority: float = Field(description="Authority weight of the source, 0–1.")
    evidence_span_indices: list[int] = Field(
        default_factory=list,
        description="Indices of sentence spans in the ingested document that support this claim.",
    )


class EventOut(BaseModel):
    event_time: str = Field(description="ISO date or datetime of the development.")
    description: str = Field(description="What happened.")
    entities: list[str] = Field(
        default_factory=list,
        description="Named entities involved in the event.",
    )
    claim_refs: list[int] = Field(
        default_factory=list,
        description="Indices into the claims list of this bundle that back the event.",
    )


class HypothesisOut(BaseModel):
    statement: str = Field(description="Competing explanation or interpretation.")
    confidence: float = Field(description="Current confidence, 0–1.")
    supporting_claim_ids: list[int] = Field(
        default_factory=list,
        description="Claim indices or IDs that support this hypothesis.",
    )
    contradicting_claim_ids: list[int] = Field(
        default_factory=list,
        description="Claim indices or IDs that contradict this hypothesis.",
    )
    invalidation_criteria: str = Field(
        description="What evidence would retire or invalidate this hypothesis."
    )
    status: str = Field(
        default="active",
        description="One of: active | leading | retired | invalidated.",
    )


class PredictionOut(BaseModel):
    statement: str = Field(description="Forecast statement.")
    probability: float = Field(description="Estimated probability, 0–1.")
    horizon_days: int = Field(description="Days until the prediction should resolve.")
    resolution_criteria: str = Field(description="Criteria for scoring hit, miss, or expired.")


class NarrativeUpdate(BaseModel):
    """Complete output of one daily synthesis call for one topic. See Nexus/SPEC.md §5.3."""

    source_profiles: list[SourceProfileOut] = Field(
        default_factory=list,
        description="Source reliability profiles extracted from today's material.",
    )
    claims: list[ClaimOut] = Field(
        default_factory=list,
        description="New or updated source-backed claims from today's material.",
    )
    events: list[EventOut] = Field(
        default_factory=list,
        description="Time-stamped developments backed by claims.",
    )
    superseded_claim_ids: list[int] = Field(
        default_factory=list,
        description="Indices or IDs of prior claims superseded or contradicted by new evidence.",
    )
    narrative_summary: str = Field(description="The new living interpretation of the topic.")
    change_summary: str = Field(
        description="What changed vs the previous narrative version and why (cite claims/sources)."
    )
    hypotheses: list[HypothesisOut] = Field(
        default_factory=list,
        description="Competing hypotheses with updated confidence and claim links.",
    )
    predictions: list[PredictionOut] = Field(
        default_factory=list,
        description="Scored forecasts tied to the updated understanding.",
    )
    briefing_markdown: str = Field(
        description="User-facing briefing section. Empty when nothing_significant is True."
    )
    nothing_significant: bool = Field(
        default=False,
        description=(
            "Set True when today's material contains nothing worth reporting. "
            "Produces a one-line entry. This is a first-class output — use it when warranted."
        ),
    )


class TopicAnalysis(BaseModel):
    """DEPRECATED: superseded by NarrativeUpdate; slated for removal in cutover phase (task F).

    Complete output of one analyst run for one topic.
    """

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
            "Full replacement dossier text if it changed. None to leave the dossier unchanged."
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


class DiscoveryCandidate(BaseModel):
    url: str = Field(description="Feed or site URL of the proposed source.")
    domain: str = Field(default="", description="Bare domain, e.g. example.com.")
    rationale: str = Field(
        description="The specific gap in current coverage this source would fill."
    )


class DiscoveryOutput(BaseModel):
    """Output of one weekly source-discovery run for one topic. See SPEC §11."""

    candidates: list[DiscoveryCandidate] = Field(
        default_factory=list,
        description="3–5 proposed candidate sources.",
    )


class WeeklyReviewOutput(BaseModel):
    """Output of one weekly compaction/review run for one topic. See SPEC §8."""

    dossier_rewrite: str | None = Field(
        default=None,
        description=(
            "Full replacement dossier text incorporating promoted insights and a short self-review "
            "note. None to leave the dossier unchanged."
        ),
    )
    promoted_observation_ids: list[int] = Field(
        default_factory=list,
        description=(
            "IDs of observations that proved durable and are now merged into the dossier; "
            "they will be marked 'promoted'."
        ),
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Optional short notes on what changed this week (for logging).",
    )
