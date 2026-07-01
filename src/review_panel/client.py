"""Thin async wrapper around the Anthropic Messages API.

Every panel call is a *forced tool call*: we pin ``tool_choice`` to a single tool
so the model must return a structured object matching that tool's schema. The
wrapper also aggregates token usage (including prompt-cache hits) so the CLI can
report cost/caching at the end.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from anthropic import AsyncAnthropic
from anthropic import APIStatusError, RateLimitError

_MAX_RETRIES = 5
_BASE_BACKOFF = 2.0  # seconds


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    calls: int = 0

    def add(self, u) -> None:
        self.calls += 1
        self.input_tokens += getattr(u, "input_tokens", 0) or 0
        self.output_tokens += getattr(u, "output_tokens", 0) or 0
        self.cache_creation_input_tokens += getattr(u, "cache_creation_input_tokens", 0) or 0
        self.cache_read_input_tokens += getattr(u, "cache_read_input_tokens", 0) or 0


@dataclass
class Client:
    """Wraps AsyncAnthropic and accumulates usage across all calls."""

    model: str
    api_key: str | None = None
    _client: AsyncAnthropic = field(init=False)
    usage: Usage = field(default_factory=Usage)

    def __post_init__(self) -> None:
        self._client = AsyncAnthropic(api_key=self.api_key) if self.api_key else AsyncAnthropic()

    async def call_tool(
        self,
        *,
        system: str,
        content: list[dict],
        tool: dict,
        max_tokens: int,
        model: str | None = None,
    ) -> dict:
        """Run one forced-tool call and return the tool input dict.

        Retries with exponential backoff on rate limits / transient 5xx.
        """
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.messages.create(
                    model=model or self.model,
                    max_tokens=max_tokens,
                    system=system,
                    tools=[tool],
                    tool_choice={"type": "tool", "name": tool["name"]},
                    messages=[{"role": "user", "content": content}],
                )
                self.usage.add(resp.usage)
                return _extract_tool_input(resp, tool["name"])
            except (RateLimitError, APIStatusError) as exc:
                # Only retry on rate limits and server-side errors.
                status = getattr(exc, "status_code", None)
                if isinstance(exc, RateLimitError) or (status is not None and status >= 500):
                    last_exc = exc
                    await asyncio.sleep(_BASE_BACKOFF * (2**attempt))
                    continue
                raise
        assert last_exc is not None
        raise last_exc


def _extract_tool_input(resp, tool_name: str) -> dict:
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return dict(block.input)
    raise RuntimeError(
        f"Model did not return the forced tool '{tool_name}' "
        f"(stop_reason={getattr(resp, 'stop_reason', None)})."
    )
