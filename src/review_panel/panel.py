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
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from .client import Client, Usage
from .config import Reviewer
from .pdf import PdfDoc
from .schemas import META_REVIEW_TOOL, REVIEW_TOOL, to_output_schema
from .triage import triage

EventHook = Callable[[str], None] | None

# Run the default roster in parallel per phase. Calls are single-turn and
# client.py retries on rate limits. Lower to 4-5 if your tier trips.
DEFAULT_CONCURRENCY = 8


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


async def _review_independent(
    client: Client, reviewer: Reviewer, doc_blocks: list, field_: str, subfield: str
) -> dict:
    system = reviewer.render_system_prompt(field_, subfield)
    prompt = (
        "The paper text and its page images are provided above. Review it from your "
        "assigned perspective. Inspect the figures and tables directly in the page "
        "images. Then return your structured review."
    )
    return await client.run(
        system=system,
        prompt=prompt,
        schema=to_output_schema(REVIEW_TOOL),
        doc_blocks=doc_blocks,
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
    doc_blocks: list,
    field_: str,
    subfield: str,
    own_prev: dict,
    peer_digest: str,
) -> dict:
    system = reviewer.render_system_prompt(field_, subfield)
    prompt = (
        "This is the reviewer discussion phase. The paper text and page images are "
        "provided above. Below is your own previous review, followed by your "
        "co-reviewers' reviews. Reconsider your assessment in light of their points: "
        "you may keep or change your score. If you change it, set score_change_reason. "
        "Re-inspect the figures/tables if relevant. Then return your (possibly revised) "
        "structured review.\n\n"
        f"## Your previous review\nScore {own_prev.get('score')}/10. "
        f"Summary: {own_prev.get('summary', '')}\n\n"
        f"## Co-reviewers' reviews\n{peer_digest}"
    )
    return await client.run(
        system=system,
        prompt=prompt,
        schema=to_output_schema(REVIEW_TOOL),
        doc_blocks=doc_blocks,
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


async def _area_chair(client: Client, doc_blocks: list, tri: dict, records: list[ReviewRecord]) -> dict:
    system = (
        "You are the Area Chair for a competitive venue. You have the paper (its text "
        "and page images are provided) and the panel's reviews. Weigh each reviewer's "
        "confidence, resolve or surface disagreements honestly, and issue a fair "
        "recommendation. Do not simply average scores. Return the structured meta-review."
    )
    prompt = (
        f"Paper: {tri.get('title')} (field: {tri.get('field')} / {tri.get('subfield')}; "
        f"type: {tri.get('paper_type')}).\n\n"
        f"Here are the reviews:\n\n{_format_reviews_for_ac(records)}\n\n"
        "Synthesise them and return the structured meta-review."
    )
    return await client.run(
        system=system,
        prompt=prompt,
        schema=to_output_schema(META_REVIEW_TOOL),
        doc_blocks=doc_blocks,
    )


async def run_panel(
    pdf: PdfDoc,
    reviewers: list[Reviewer],
    *,
    client: Client,
    rounds: int,
    concurrency: int = DEFAULT_CONCURRENCY,
    on_event: EventHook = None,
) -> PanelResult:
    sem = asyncio.Semaphore(concurrency)

    async def _bounded(reviewer: Reviewer, label: str, coro: Awaitable[dict]) -> dict:
        async with sem:
            _emit(on_event, f"  → {reviewer.name} — {label} started…")
            t0 = time.monotonic()
            rev = await coro
            dt = time.monotonic() - t0
            _emit(
                on_event,
                f"  ✓ {reviewer.name} — {label} done in {dt:.0f}s "
                f"(score {rev.get('score', '?')}/10)",
            )
            return rev

    # Parse the paper once; every call reuses these text + image blocks.
    doc_blocks = pdf.content_blocks()

    _emit(on_event, "Triaging paper (detecting field)…")
    tri = await triage(client, doc_blocks)
    field_, subfield = tri["field"], tri["subfield"]
    _emit(on_event, f"Field: {field_} / {subfield}. Running {len(reviewers)} independent reviews…")

    round0 = await asyncio.gather(
        *[
            _bounded(r, "independent review", _review_independent(client, r, doc_blocks, field_, subfield))
            for r in reviewers
        ]
    )
    histories: dict[str, list[dict]] = {r.key: [rev] for r, rev in zip(reviewers, round0)}

    for i in range(rounds):
        _emit(on_event, f"Discussion round {i + 1}/{rounds}…")
        current = {r.key: histories[r.key][-1] for r in reviewers}
        results = await asyncio.gather(
            *[
                _bounded(
                    r,
                    f"discussion round {i + 1}",
                    _review_discussion(
                        client, r, doc_blocks, field_, subfield, current[r.key],
                        _peer_digest(reviewers, current, exclude=r.key),
                    ),
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
    meta = await _area_chair(client, doc_blocks, tri, records)

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
