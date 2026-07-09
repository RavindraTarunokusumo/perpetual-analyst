"""Pydantic output models for the analyst's structured response. See SPEC §7.

NOTE: Numeric range constraints (ge/le) are intentionally absent from fields that appear in
provider-facing structured-output schemas. OpenRouter's Anthropic backend rejects JSON-schema
properties ``minimum`` and ``maximum`` on integer/number types. Valid ranges are enforced by
clamping field_validators instead, which correct out-of-range model output without serialising
into the JSON schema.
"""

from pydantic import BaseModel, Field


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
        description=(
            "0-based indices into the claims array you emit in THIS response "
            "(not the prior [P#] list)."
        ),
    )


class HypothesisOut(BaseModel):
    statement: str = Field(description="Competing explanation or interpretation.")
    confidence: float = Field(description="Current confidence, 0–1.")
    supporting_claim_ids: list[int] = Field(
        default_factory=list,
        description=(
            "0-based indices into the claims array you emit in THIS response "
            "(not the prior [P#] list)."
        ),
    )
    contradicting_claim_ids: list[int] = Field(
        default_factory=list,
        description=(
            "0-based indices into the claims array you emit in THIS response "
            "(not the prior [P#] list)."
        ),
    )
    invalidation_criteria: str = Field(
        description="What evidence would retire or invalidate this hypothesis."
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
        description=(
            "0-based indices into the ACTIVE CLAIMS (prior) [P#] list superseded or "
            "contradicted by new evidence."
        ),
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
