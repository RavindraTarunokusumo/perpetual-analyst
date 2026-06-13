from __future__ import annotations

import json

from perpetual_analyst.analyst.schemas import (
    DigestOutput,
    NewObservation,
    ThesisUpdate,
    TopicAnalysis,
)


def test_schema_has_no_numeric_bounds():
    # OpenRouter's Anthropic provider rejects minimum/maximum in structured-output schemas
    schema = json.dumps(TopicAnalysis.model_json_schema())
    assert '"minimum"' not in schema
    assert '"maximum"' not in schema


def test_importance_clamped():
    assert NewObservation(kind="fact", content="x", importance=5).importance == 3
    assert NewObservation(kind="fact", content="x", importance=0).importance == 1
    assert NewObservation(kind="fact", content="x", importance=2).importance == 2


def test_confidence_clamped():
    up = ThesisUpdate(statement="s", confidence=1.7, change_rationale="r")
    assert up.confidence == 1.0
    assert ThesisUpdate(statement="s", confidence=-0.2, change_rationale="r").confidence == 0.0


def test_digest_output_schema_is_provider_safe():
    schema = json.dumps(DigestOutput.model_json_schema())
    assert '"minimum"' not in schema and '"maximum"' not in schema
    out = DigestOutput(executive_summary="s", digest_text="d")
    assert out.digest_text == "d"
