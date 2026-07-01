"""Panel orchestration: independent reviews -> discussion -> area-chair meta-review.

This mirrors a real program committee:
  * Round 0 - every reviewer reviews the paper **independently and in parallel**
    (no visibility of peers), which preserves independence and avoids anchoring.
  * Discussion rounds - each reviewer now sees a digest of the *other* reviews and
    may revise their score/critique, recording why it changed.
  * Area Chair - reads the paper plus the final reviews and writes a meta-review
    with an accept / minor / major / reject recommendation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from .client import Client, Usage
from .config import META_MAX_TOKENS, REVIEW_MAX_TOKENS, Reviewer
from .pdf import PdfDoc
from .schemas import META_REVIEW_TOOL, REVIEW_TOOL
from .triage import triage

EventHook = Callable[[str], None] | None


@dataclass
class ReviewRecord:
    key: str
    name: str
    focus: str
    review: dict              # final-round review (submit_review input)
    initial_score: int
    final_score: int
    history: list[dict]       # one review dict per round (index 0 = independent)


@dataclass
class PanelResult:
    pdf_source: str
    filename: str
    n_pages: int
    model: str
    rounds_run: int
    triage: dict
    reviews: list[ReviewRecord]
    meta_review: dict
    usage: Usage


def _emit(hook: EventHook, msg: str) -> None:
    if hook is not None:
        hook(msg)


def _review_content(pdf: PdfDoc, instruction: str, cache: bool) -> list[dict]:
    return [pdf.document_block(cache=cache), {"type": "text", "text": instruction}]


async def _review_independent(
    client: Client, reviewer: Reviewer, pdf: PdfDoc, field_: str, subfield: str, cache: bool
) -> dict:
    system = reviewer.render_system_prompt(field_, subfield)
    instruction = (
        "Review this paper from your assigned perspective. Inspect the figures and "
        "tables directly. Then call submit_review with your structured review."
    )
    return await client.call_tool(
        system=system,
        content=_review_content(pdf, instruction, cache),
        tool=REVIEW_TOOL,
        max_tokens=REVIEW_MAX_TOKENS,
    )


def _peer_digest(reviewers: list[Reviewer], current: dict[str, dict], exclude: str) -> str:
    lines: list[str] = []
    by_key = {r.key: r for r in reviewers}
    for key, rev in current.items():
        if key == exclude:
            continue
        name = by_key[key].name
        weak = "; ".join(w["issue"] for w in rev.get("weaknesses", [])[:3])
        lines.append(
            f"### {name} (score {rev.get('score')}/10, confidence {rev.get('confidence')}/5)\n"
            f"Summary: {rev.get('summary', '')}\n"
            f"Top concerns: {weak or 'none stated'}"
        )
    return "\n\n".join(lines)


async def _review_discussion(
    client: Client,
    reviewer: Reviewer,
    pdf: PdfDoc,
    field_: str,
    subfield: str,
    own_prev: dict,
    peer_digest: str,
    cache: bool,
) -> dict:
    system = reviewer.render_system_prompt(field_, subfield)
    instruction = (
        "This is the reviewer discussion phase. Below is your own previous review, "
        "followed by your co-reviewers' reviews. Reconsider your assessment in light "
        "of their points: you may keep or change your score. If you change it, set "
        "score_change_reason. Re-inspect the figures/tables if relevant. Then call "
        "submit_review with your (possibly revised) review.\n\n"
        f"## Your previous review\nScore {own_prev.get('score')}/10. "
        f"Summary: {own_prev.get('summary', '')}\n\n"
        f"## Co-reviewers' reviews\n{peer_digest}"
    )
    return await client.call_tool(
        system=system,
        content=_review_content(pdf, instruction, cache),
        tool=REVIEW_TOOL,
        max_tokens=REVIEW_MAX_TOKENS,
    )


def _format_reviews_for_ac(records: list[ReviewRecord]) -> str:
    blocks: list[str] = []
    for r in records:
        rev = r.review
        weak = "\n".join(f"  - {w['issue']} (fix: {w['actionable_fix']})" for w in rev.get("weaknesses", []))
        delta = ""
        if r.final_score != r.initial_score:
            delta = f" (revised from {r.initial_score}; {rev.get('score_change_reason', '')})"
        blocks.append(
            f"## {r.name} — score {r.final_score}/10, confidence {rev.get('confidence')}/5{delta}\n"
            f"Summary: {rev.get('summary', '')}\n"
            f"Strengths: {'; '.join(rev.get('strengths', []))}\n"
            f"Weaknesses:\n{weak}\n"
            f"Questions: {'; '.join(rev.get('questions', []))}"
        )
    return "\n\n".join(blocks)


async def _area_chair(client: Client, pdf: PdfDoc, tri: dict, records: list[ReviewRecord], cache: bool) -> dict:
    system = (
        "You are the Area Chair for a competitive venue. You have the paper (attached "
        "PDF) and the panel's reviews. Weigh each reviewer's confidence, resolve or "
        "surface disagreements honestly, and issue a fair recommendation. Do not simply "
        "average scores. Call submit_meta_review."
    )
    instruction = (
        f"Paper: {tri.get('title')} (field: {tri.get('field')} / {tri.get('subfield')}; "
        f"type: {tri.get('paper_type')}).\n\n"
        f"Here are the reviews:\n\n{_format_reviews_for_ac(records)}\n\n"
        "Synthesise them and call submit_meta_review."
    )
    return await client.call_tool(
        system=system,
        content=_review_content(pdf, instruction, cache),
        tool=META_REVIEW_TOOL,
        max_tokens=META_MAX_TOKENS,
    )


async def run_panel(
    pdf: PdfDoc,
    reviewers: list[Reviewer],
    *,
    client: Client,
    rounds: int,
    cache: bool = True,
    on_event: EventHook = None,
) -> PanelResult:
    _emit(on_event, "Triaging paper (detecting field)…")
    tri = await triage(client, pdf, cache)
    field_, subfield = tri["field"], tri["subfield"]
    _emit(on_event, f"Field: {field_} / {subfield}. Running {len(reviewers)} independent reviews…")

    round0 = await asyncio.gather(
        *[_review_independent(client, r, pdf, field_, subfield, cache) for r in reviewers]
    )
    histories: dict[str, list[dict]] = {r.key: [rev] for r, rev in zip(reviewers, round0)}

    for i in range(rounds):
        _emit(on_event, f"Discussion round {i + 1}/{rounds}…")
        current = {r.key: histories[r.key][-1] for r in reviewers}
        results = await asyncio.gather(
            *[
                _review_discussion(
                    client, r, pdf, field_, subfield, current[r.key],
                    _peer_digest(reviewers, current, exclude=r.key), cache,
                )
                for r in reviewers
            ]
        )
        for r, rev in zip(reviewers, results):
            histories[r.key].append(rev)

    records = [
        ReviewRecord(
            key=r.key,
            name=r.name,
            focus=r.focus,
            review=histories[r.key][-1],
            initial_score=int(histories[r.key][0].get("score", 0)),
            final_score=int(histories[r.key][-1].get("score", 0)),
            history=histories[r.key],
        )
        for r in reviewers
    ]

    _emit(on_event, "Area Chair writing meta-review…")
    meta = await _area_chair(client, pdf, tri, records, cache)

    return PanelResult(
        pdf_source=pdf.source,
        filename=pdf.filename,
        n_pages=pdf.n_pages,
        model=client.model,
        rounds_run=rounds,
        triage=tri,
        reviews=records,
        meta_review=meta,
        usage=client.usage,
    )
