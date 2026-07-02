"""Model layer, built on the Claude Agent SDK.

Every panel call runs a session via ``claude_agent_sdk.query`` that authenticates
through the Claude Code CLI subscription (no ``ANTHROPIC_API_KEY``). The paper is
parsed once (see ``pdf.py``) and sent **inline** as message content — the extracted
text plus one image per page — so each reviewer sees the figures and tables without
re-opening the file. No tools are needed, so each call is a single fast turn. The
call is pinned to a JSON schema via ``output_format`` so the result is a structured
object. Token usage is aggregated across all calls.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

_MAX_RETRIES = 5
_BASE_BACKOFF = 8.0  # seconds; grows exponentially to ride out rate limits
_MAX_TURNS = 2  # the paper is inline; one turn to answer (spare turn for safety)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    calls: int = 0

    def add(self, u: dict | None) -> None:
        self.calls += 1
        if not u:
            return
        self.input_tokens += u.get("input_tokens", 0) or 0
        self.output_tokens += u.get("output_tokens", 0) or 0
        self.cache_creation_input_tokens += u.get("cache_creation_input_tokens", 0) or 0
        self.cache_read_input_tokens += u.get("cache_read_input_tokens", 0) or 0


@dataclass
class Client:
    """Drives Agent SDK sessions and accumulates usage across all calls."""

    model: str
    usage: Usage = field(default_factory=Usage)

    async def run(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict,
        doc_blocks: list[dict[str, Any]],
    ) -> dict:
        """Run one structured session and return the result object.

        ``doc_blocks`` are the shared paper content blocks (text + page images);
        ``prompt`` is the per-call instruction appended after them. Retries with
        exponential backoff on transient failures.
        """
        options = ClaudeAgentOptions(
            system_prompt=system,
            model=self.model,
            allowed_tools=[],  # paper is inline — no tools needed
            setting_sources=[],  # don't inherit this repo's CLAUDE.md / settings
            permission_mode="bypassPermissions",
            max_turns=_MAX_TURNS,
            output_format={"type": "json_schema", "schema": schema},
        )
        content = [*doc_blocks, {"type": "text", "text": prompt}]

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                result = await self._collect(content, options)
                self.usage.add(result[1])
                return result[0]
            except Exception as exc:  # noqa: BLE001 - retry any transient failure
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BASE_BACKOFF * (2**attempt))
                    continue
                raise
        assert last_exc is not None
        raise last_exc

    async def _collect(
        self, content: list[dict[str, Any]], options: ClaudeAgentOptions
    ) -> tuple[dict, dict | None]:
        """Run the session and return ``(structured_object, usage_dict)``."""

        async def _stream():
            yield {"type": "user", "message": {"role": "user", "content": content}}

        result_msg: ResultMessage | None = None
        async for msg in query(prompt=_stream(), options=options):
            if isinstance(msg, ResultMessage):
                result_msg = msg

        if result_msg is None:
            raise RuntimeError("Agent session ended without a ResultMessage.")
        if result_msg.is_error:
            raise RuntimeError(
                f"Agent session failed: {result_msg.subtype} "
                f"({'; '.join(result_msg.errors or [])})"
            )

        data = result_msg.structured_output
        if data is None:
            data = _parse_json(result_msg.result)
        if not isinstance(data, dict):
            raise RuntimeError("Agent session did not return a JSON object.")
        return data, result_msg.usage


def _parse_json(text: str | None) -> dict | None:
    """Best-effort JSON extraction from a text result."""
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None
