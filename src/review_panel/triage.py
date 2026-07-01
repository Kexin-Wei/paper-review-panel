"""Detect the paper's field/type so the domain reviewer can adapt."""

from __future__ import annotations

from .client import Client
from .config import TRIAGE_MAX_TOKENS
from .pdf import PdfDoc
from .schemas import TRIAGE_TOOL

_TRIAGE_SYSTEM = (
    "You are an editorial assistant triaging a submitted paper (attached as a PDF). "
    "Identify its title, primary research field, subfield, and paper type so the "
    "correct expert reviewers can be assigned. Call submit_triage with your findings."
)


async def triage(client: Client, pdf: PdfDoc, cache: bool = True) -> dict:
    content = [
        pdf.document_block(cache=cache),
        {"type": "text", "text": "Triage this paper. Call submit_triage."},
    ]
    result = await client.call_tool(
        system=_TRIAGE_SYSTEM,
        content=content,
        tool=TRIAGE_TOOL,
        max_tokens=TRIAGE_MAX_TOKENS,
    )
    # Fill defaults so downstream formatting never KeyErrors.
    result.setdefault("title", "(untitled)")
    result.setdefault("field", "the paper's field")
    result.setdefault("subfield", "the relevant subfield")
    result.setdefault("paper_type", "other")
    return result
