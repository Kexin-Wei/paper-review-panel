"""Defaults, reviewer roster loading, and shared prompt text."""

from __future__ import annotations

import importlib.resources as resources
from dataclasses import dataclass

import yaml

# Model IDs (see /claude-api for the current list).
DEFAULT_MODEL = "claude-opus-4-8"

DEFAULT_ROUNDS = 1          # discussion rounds after the independent round (0 = single-pass)
DEFAULT_MAX_PAGES = 100     # PDF page ceiling
MAX_PDF_BYTES = 32 * 1024 * 1024  # 32 MB ceiling
DEFAULT_OUT_DIR = "out"     # fallback output dir when the source is a URL
JSON_ONLY = False           # when True, skip the Markdown report and write only JSON

# Prepended to every reviewer's system prompt.
SHARED_PREAMBLE = (
    "You are an expert peer reviewer on a program committee. The paper under review is "
    "provided to you directly: first its full extracted text, then one image per page "
    "showing the exact layout (so you can see all figures, tables, and equations). Read "
    "the whole paper. Be specific, fair, and constructive; ground every point in the "
    "actual content and cite sections, figures, and tables by number. Make weaknesses "
    "actionable. Return your assessment as the required structured review object."
)


@dataclass(frozen=True)
class Reviewer:
    key: str
    name: str
    focus: str
    system_prompt: str

    def render_system_prompt(self, field: str, subfield: str) -> str:
        """Fill {field}/{subfield} placeholders and prepend the shared preamble."""
        body = self.system_prompt.format(field=field, subfield=subfield)
        return f"{SHARED_PREAMBLE}\n\nYour perspective — {self.name} ({self.focus}):\n{body}"


def load_roster() -> list[Reviewer]:
    """Load the reviewer roster shipped alongside this package."""
    text = resources.files("review_panel").joinpath("reviewers.yaml").read_text("utf-8")
    entries = yaml.safe_load(text)
    return [
        Reviewer(
            key=e["key"],
            name=e["name"],
            focus=e["focus"],
            system_prompt=e["system_prompt"].strip(),
        )
        for e in entries
    ]


def select_reviewers(keys: list[str] | None) -> list[Reviewer]:
    """Return the full roster, or the subset whose keys match ``keys`` (in order)."""
    roster = load_roster()
    if not keys:
        return roster
    by_key = {r.key: r for r in roster}
    missing = [k for k in keys if k not in by_key]
    if missing:
        available = ", ".join(by_key)
        raise ValueError(f"Unknown reviewer(s): {', '.join(missing)}. Available: {available}")
    return [by_key[k] for k in keys]
