"""Detect the paper's field/type so the domain reviewer can adapt."""

from __future__ import annotations

from .client import Client
from .schemas import TRIAGE_TOOL, to_output_schema

_TRIAGE_SYSTEM = (
    "You are an editorial assistant triaging a submitted paper. Its text and page "
    "images are provided. Identify its title, primary research field, subfield, and "
    "paper type so the correct expert reviewers can be assigned. Return your findings "
    "as the required structured triage object."
)


async def triage(client: Client, doc_blocks: list) -> dict:
    prompt = (
        "The paper text and page images are provided above. Triage it and return the "
        "structured result."
    )
    result = await client.run(
        system=_TRIAGE_SYSTEM,
        prompt=prompt,
        schema=to_output_schema(TRIAGE_TOOL),
        doc_blocks=doc_blocks,
    )
    # Fill defaults so downstream formatting never KeyErrors.
    result.setdefault("title", "(untitled)")
    result.setdefault("field", "the paper's field")
    result.setdefault("subfield", "the relevant subfield")
    result.setdefault("paper_type", "other")
    return result
