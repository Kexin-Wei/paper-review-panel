"""JSON schemas that make every model call return a parseable structured object.

Each reviewer/triage/area-chair call runs through the Claude Agent SDK with
``output_format={"type": "json_schema", "schema": ...}``, so the model's final
result is a structured object matching the schema instead of free-form prose.
``to_output_schema`` adapts the schemas below into a form the structured-output
compiler accepts.
"""

from __future__ import annotations

import copy

# --- Triage: detect the paper's field so the domain reviewer can adapt --------
TRIAGE_TOOL = {
    "name": "submit_triage",
    "description": "Record structured metadata about the paper under review.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "The paper's title."},
            "field": {
                "type": "string",
                "description": "Primary research field, e.g. 'Machine Learning', "
                "'Systems Security', 'Molecular Biology', 'Health Economics'.",
            },
            "subfield": {
                "type": "string",
                "description": "More specific area, e.g. 'diffusion models', "
                "'consensus protocols', 'single-cell RNA-seq'.",
            },
            "paper_type": {
                "type": "string",
                "enum": [
                    "empirical",
                    "theoretical",
                    "methods",
                    "systems",
                    "survey",
                    "position",
                    "dataset_or_benchmark",
                    "other",
                ],
            },
            "venue_guess": {
                "type": "string",
                "description": "A plausible target venue, if inferable.",
            },
            "keywords": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "field", "subfield", "paper_type"],
    },
}

# --- A single reviewer's structured review ------------------------------------
REVIEW_TOOL = {
    "name": "submit_review",
    "description": "Submit your structured peer review of the paper.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "2-3 sentence summary of the paper in your own words.",
            },
            "strengths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Concrete strengths, most important first.",
            },
            "weaknesses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "issue": {"type": "string"},
                        "actionable_fix": {
                            "type": "string",
                            "description": "A specific, actionable suggestion to address the issue.",
                        },
                    },
                    "required": ["issue", "actionable_fix"],
                },
            },
            "figures_assessed": {
                "type": "array",
                "description": "Assessment of specific figures/tables you inspected. "
                "Reference them by number (e.g. 'Figure 3', 'Table 2').",
                "items": {
                    "type": "object",
                    "properties": {
                        "figure": {"type": "string"},
                        "assessment": {"type": "string"},
                    },
                    "required": ["figure", "assessment"],
                },
            },
            "questions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Questions for the authors.",
            },
            "score": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "description": "Overall score, 1 (reject) to 10 (award-worthy).",
            },
            "confidence": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "Your confidence in this assessment, 1 (low) to 5 (expert).",
            },
            "score_change_reason": {
                "type": "string",
                "description": "If this is a discussion round and you changed your score, "
                "explain why. Leave empty otherwise.",
            },
        },
        "required": [
            "summary",
            "strengths",
            "weaknesses",
            "figures_assessed",
            "questions",
            "score",
            "confidence",
        ],
    },
}

# --- Area Chair meta-review ----------------------------------------------------
META_REVIEW_TOOL = {
    "name": "submit_meta_review",
    "description": "Submit the Area Chair meta-review and final recommendation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "synthesis": {
                "type": "string",
                "description": "A synthesis of the reviews and the paper's overall standing.",
            },
            "agreements": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Points the reviewers broadly agree on.",
            },
            "disagreements": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Points of disagreement between reviewers, and your read on them.",
            },
            "recommendation": {
                "type": "string",
                "enum": ["accept", "minor_revision", "major_revision", "reject"],
            },
            "justification": {
                "type": "string",
                "description": "Justification for the recommendation.",
            },
            "per_reviewer_notes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "reviewer": {"type": "string"},
                        "note": {"type": "string"},
                    },
                    "required": ["reviewer", "note"],
                },
            },
        },
        "required": [
            "synthesis",
            "agreements",
            "disagreements",
            "recommendation",
            "justification",
        ],
    },
}

# --- Structured-output adaptation ---------------------------------------------
# The structured-output compiler requires ``additionalProperties: false`` on every
# object and rejects numeric/length constraints. The tool dicts above keep those
# constraints (they document intent and are asserted in tests); this helper emits
# a compiler-friendly copy of a tool's ``input_schema``.
_UNSUPPORTED_KEYS = ("minimum", "maximum", "minLength", "maxLength", "multipleOf")


def _sanitize(node: object) -> object:
    if isinstance(node, dict):
        clean = {k: _sanitize(v) for k, v in node.items() if k not in _UNSUPPORTED_KEYS}
        if clean.get("type") == "object":
            clean.setdefault("additionalProperties", False)
        return clean
    if isinstance(node, list):
        return [_sanitize(v) for v in node]
    return node


def to_output_schema(tool: dict) -> dict:
    """Return a structured-output-ready JSON schema from a tool's ``input_schema``.

    Deep-copies the schema, strips constraints the compiler rejects, and sets
    ``additionalProperties: false`` on every object.
    """
    return _sanitize(copy.deepcopy(tool["input_schema"]))  # type: ignore[return-value]
