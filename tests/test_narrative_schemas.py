"""Tests for narrative-update output schemas (NarrativeUpdate bundle)."""

from __future__ import annotations

from perpetual_analyst.analyst.schemas import (
    ClaimOut,
    EventOut,
    HypothesisOut,
    NarrativeUpdate,
    PredictionOut,
    SourceProfileOut,
)


def test_narrative_update_fully_populated_round_trips() -> None:
    update = NarrativeUpdate(
        source_profiles=[
            SourceProfileOut(
                source_type="news",
                incentive_note="Commercial wire service.",
                reliability=0.85,
            )
        ],
        claims=[
            ClaimOut(
                claim_text="Vendor X shipped a 1M-context window.",
                entities=["Vendor X"],
                confidence=0.9,
                source_authority=0.8,
                evidence_span_indices=[0, 2],
            )
        ],
        events=[
            EventOut(
                event_time="2026-07-08T12:00:00Z",
                description="Vendor X announced a 1M-context product.",
                entities=["Vendor X"],
                claim_refs=[0],
            )
        ],
        superseded_claim_ids=[3],
        narrative_summary="Long-context windows are becoming a baseline capability.",
        change_summary="Previously capped at 128k; claim [0] from today's wire shifts the view.",
        hypotheses=[
            HypothesisOut(
                statement="Context scaling will commoditize within 12 months.",
                confidence=0.65,
                supporting_claim_ids=[0],
                contradicting_claim_ids=[],
                invalidation_criteria="No major vendor ships 1M+ context by 2027-01.",
                status="leading",
            )
        ],
        predictions=[
            PredictionOut(
                statement="At least two frontier labs ship 1M context by year-end.",
                probability=0.6,
                horizon_days=180,
                resolution_criteria="Public product pages list 1M+ context.",
            )
        ],
        briefing_markdown="## AI context windows\n\nVendor X moved the bar to 1M tokens.",
        nothing_significant=False,
    )

    dumped = update.model_dump()
    restored = NarrativeUpdate.model_validate(dumped)

    assert restored == update
    assert len(restored.source_profiles) == 1
    assert len(restored.claims) == 1
    assert len(restored.events) == 1
    assert len(restored.hypotheses) == 1
    assert len(restored.predictions) == 1
    assert restored.superseded_claim_ids == [3]
    assert restored.nothing_significant is False


def test_narrative_update_minimal_nothing_significant_round_trips() -> None:
    update = NarrativeUpdate(
        narrative_summary="",
        change_summary="",
        briefing_markdown="",
        nothing_significant=True,
    )

    dumped = update.model_dump()
    restored = NarrativeUpdate.model_validate(dumped)

    assert restored == update
    assert restored.nothing_significant is True
    assert restored.source_profiles == []
    assert restored.claims == []
    assert restored.events == []
    assert restored.superseded_claim_ids == []
    assert restored.hypotheses == []
    assert restored.predictions == []
