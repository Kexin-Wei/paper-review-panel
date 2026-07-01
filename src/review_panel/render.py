"""Render a PanelResult to JSON and a human-readable Markdown report."""

from __future__ import annotations

import json
from dataclasses import asdict

from .panel import PanelResult

_REC_LABELS = {
    "accept": "Accept",
    "minor_revision": "Minor revision",
    "major_revision": "Major revision",
    "reject": "Reject",
}


def to_dict(result: PanelResult) -> dict:
    """Full structured result, JSON-serialisable."""
    return {
        "paper": {
            "source": result.pdf_source,
            "filename": result.filename,
            "n_pages": result.n_pages,
        },
        "model": result.model,
        "rounds_run": result.rounds_run,
        "triage": result.triage,
        "reviews": [
            {
                "key": r.key,
                "name": r.name,
                "focus": r.focus,
                "initial_score": r.initial_score,
                "final_score": r.final_score,
                "review": r.review,
                "history": r.history,
            }
            for r in result.reviews
        ],
        "meta_review": result.meta_review,
        "usage": asdict(result.usage),
    }


def to_json(result: PanelResult) -> str:
    return json.dumps(to_dict(result), indent=2, ensure_ascii=False)


def _md_list(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "_none_"


def _review_section(r) -> str:
    rev = r.review
    delta = ""
    if r.final_score != r.initial_score:
        reason = rev.get("score_change_reason", "").strip()
        delta = f" _(revised from {r.initial_score}"
        delta += f" — {reason})_" if reason else ")_"

    weaknesses = "\n".join(
        f"- **{w['issue']}**\n  - _Fix:_ {w['actionable_fix']}" for w in rev.get("weaknesses", [])
    ) or "_none_"
    figures = "\n".join(
        f"- **{f['figure']}** — {f['assessment']}" for f in rev.get("figures_assessed", [])
    ) or "_no figures explicitly assessed_"

    return (
        f"### {r.name}\n"
        f"*{r.focus}*\n\n"
        f"**Score: {r.final_score}/10**{delta} · Confidence: {rev.get('confidence')}/5\n\n"
        f"**Summary.** {rev.get('summary', '')}\n\n"
        f"**Strengths**\n{_md_list(rev.get('strengths', []))}\n\n"
        f"**Weaknesses**\n{weaknesses}\n\n"
        f"**Figures & tables assessed**\n{figures}\n\n"
        f"**Questions for the authors**\n{_md_list(rev.get('questions', []))}\n"
    )


def to_markdown(result: PanelResult) -> str:
    tri = result.triage
    meta = result.meta_review
    rec = meta.get("recommendation", "")
    rec_label = _REC_LABELS.get(rec, rec)

    # Score table
    rows = ["| Reviewer | Score | Confidence |", "| --- | --- | --- |"]
    for r in result.reviews:
        conf = r.review.get("confidence")
        cell = f"{r.final_score}/10"
        if r.final_score != r.initial_score:
            cell = f"{r.initial_score}→{r.final_score}/10"
        rows.append(f"| {r.name} | {cell} | {conf}/5 |")
    score_table = "\n".join(rows)

    u = result.usage
    cache_note = (
        f"cache write {u.cache_creation_input_tokens:,} tok, "
        f"cache read {u.cache_read_input_tokens:,} tok"
    )

    parts = [
        f"# Review Panel — {tri.get('title', result.filename)}",
        "",
        f"**Field:** {tri.get('field')} / {tri.get('subfield')} · "
        f"**Type:** {tri.get('paper_type')} · **Pages:** {result.n_pages}  ",
        f"**Source:** `{result.pdf_source}` · **Model:** {result.model} · "
        f"**Discussion rounds:** {result.rounds_run}",
        "",
        f"## Recommendation: **{rec_label}**",
        "",
        meta.get("justification", ""),
        "",
        "## Scores",
        "",
        score_table,
        "",
        "## Area Chair meta-review",
        "",
        meta.get("synthesis", ""),
        "",
        "**Points of agreement**",
        _md_list(meta.get("agreements", [])),
        "",
        "**Points of disagreement**",
        _md_list(meta.get("disagreements", [])),
        "",
        "## Reviews",
        "",
    ]
    parts.extend(_review_section(r) for r in result.reviews)
    parts.append("---")
    parts.append(
        f"_Usage: {u.calls} calls · {u.input_tokens:,} input / "
        f"{u.output_tokens:,} output tokens · {cache_note}._"
    )
    return "\n".join(parts)
