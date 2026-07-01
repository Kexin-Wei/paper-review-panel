"""Render a fixture PanelResult to Markdown/JSON without any API calls."""

from __future__ import annotations

import json

from review_panel.client import Usage
from review_panel.panel import PanelResult, ReviewRecord
from review_panel.render import to_json, to_markdown


def _review(score: int) -> dict:
    return {
        "summary": "A paper about widgets.",
        "strengths": ["Clear motivation"],
        "weaknesses": [{"issue": "Weak baseline", "actionable_fix": "Add strong baseline X"}],
        "figures_assessed": [{"figure": "Figure 2", "assessment": "Axes unlabelled"}],
        "questions": ["What is the compute budget?"],
        "score": score,
        "confidence": 4,
        "score_change_reason": "Persuaded by co-reviewer on baselines." if score == 5 else "",
    }


def _fixture() -> PanelResult:
    rec = ReviewRecord(
        key="methodology",
        name="Reviewer 1 — Methodology",
        focus="Rigor.",
        review=_review(5),
        initial_score=7,
        final_score=5,
        history=[_review(7), _review(5)],
    )
    meta = {
        "synthesis": "Borderline paper.",
        "agreements": ["Motivation is clear"],
        "disagreements": ["Reviewers split on novelty"],
        "recommendation": "major_revision",
        "justification": "Needs stronger baselines.",
        "per_reviewer_notes": [{"reviewer": "Reviewer 1", "note": "Lowered score after discussion."}],
    }
    return PanelResult(
        pdf_source="paper.pdf",
        filename="paper.pdf",
        n_pages=8,
        model="claude-opus-4-8",
        rounds_run=1,
        triage={"title": "Widgets", "field": "ML", "subfield": "widgets", "paper_type": "empirical"},
        reviews=[rec],
        meta_review=meta,
        usage=Usage(input_tokens=100, output_tokens=50, cache_read_input_tokens=80, calls=3),
    )


def test_to_json_is_valid_and_complete():
    data = json.loads(to_json(_fixture()))
    assert data["meta_review"]["recommendation"] == "major_revision"
    assert data["reviews"][0]["initial_score"] == 7
    assert data["reviews"][0]["final_score"] == 5
    assert data["usage"]["cache_read_input_tokens"] == 80


def test_to_markdown_contains_key_sections():
    md = to_markdown(_fixture())
    assert "# Review Panel — Widgets" in md
    assert "Recommendation: **Major revision**" in md
    assert "7→5/10" in md            # revised score shown in table
    assert "Figure 2" in md          # figure assessment surfaced
    assert "Persuaded by co-reviewer" in md  # score-change reason surfaced
