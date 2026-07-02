"""Sanity checks on the forced-tool schemas."""

from __future__ import annotations

from review_panel.schemas import (
    META_REVIEW_TOOL,
    REVIEW_TOOL,
    TRIAGE_TOOL,
    to_output_schema,
)


def _required(tool: dict) -> list[str]:
    return tool["input_schema"]["required"]


def test_tool_names_are_stable():
    assert TRIAGE_TOOL["name"] == "submit_triage"
    assert REVIEW_TOOL["name"] == "submit_review"
    assert META_REVIEW_TOOL["name"] == "submit_meta_review"


def test_review_schema_forces_figure_and_score():
    req = _required(REVIEW_TOOL)
    assert "figures_assessed" in req  # figure judgement is mandatory
    assert "score" in req and "confidence" in req
    score = REVIEW_TOOL["input_schema"]["properties"]["score"]
    assert score["minimum"] == 1 and score["maximum"] == 10


def test_meta_review_recommendation_enum():
    rec = META_REVIEW_TOOL["input_schema"]["properties"]["recommendation"]
    assert set(rec["enum"]) == {"accept", "minor_revision", "major_revision", "reject"}


def test_every_tool_has_object_schema():
    for tool in (TRIAGE_TOOL, REVIEW_TOOL, META_REVIEW_TOOL):
        assert tool["input_schema"]["type"] == "object"
        assert "properties" in tool["input_schema"]


def test_to_output_schema_sanitizes_for_structured_output():
    schema = to_output_schema(REVIEW_TOOL)
    # additionalProperties:false is set on every object (top-level and nested)
    assert schema["additionalProperties"] is False
    weakness = schema["properties"]["weaknesses"]["items"]
    assert weakness["additionalProperties"] is False
    # unsupported numeric constraints are stripped
    assert "minimum" not in schema["properties"]["score"]
    assert "maximum" not in schema["properties"]["score"]
    # enums are preserved, and the original tool dict is untouched
    assert set(schema["required"]) >= {"score", "confidence"}
    assert REVIEW_TOOL["input_schema"]["properties"]["score"]["minimum"] == 1
