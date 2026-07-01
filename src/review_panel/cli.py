"""Command-line entrypoint: ``review-panel <pdf-url-or-path> [flags]``."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

from . import __version__
from .client import Client
from .config import (
    DEFAULT_MAX_PAGES,
    DEFAULT_MODEL,
    DEFAULT_OUT_DIR,
    DEFAULT_ROUNDS,
    select_reviewers,
)
from .panel import run_panel
from .pdf import load_pdf
from .render import to_json, to_markdown

console = Console()
err_console = Console(stderr=True)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="review-panel",
        description="Run an agentic multi-reviewer paper review panel over a PDF "
        "(with figure judgement), powered by Claude.",
    )
    p.add_argument("pdf", help="Path or http(s) URL to the paper PDF.")
    p.add_argument(
        "--rounds", type=int, default=DEFAULT_ROUNDS,
        help=f"Reviewer discussion rounds after the independent pass (default {DEFAULT_ROUNDS}; 0 = single-pass).",
    )
    p.add_argument(
        "--reviewers", default=None,
        help="Comma-separated reviewer keys to include (default: full roster). "
        "Keys: methodology,novelty,clarity,domain_expert,reproducibility,ethics_impact,ai_style",
    )
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"Model ID (default {DEFAULT_MODEL}).")
    p.add_argument("--out", default=DEFAULT_OUT_DIR, help=f"Output directory (default {DEFAULT_OUT_DIR}).")
    p.add_argument("--json-only", action="store_true", help="Write only report.json (skip Markdown).")
    p.add_argument("--no-cache", action="store_true", help="Disable prompt caching of the PDF.")
    p.add_argument(
        "--max-pages", type=int, default=DEFAULT_MAX_PAGES,
        help=f"Reject PDFs longer than this many pages (default {DEFAULT_MAX_PAGES}).",
    )
    p.add_argument("--version", action="version", version=f"review-panel {__version__}")
    return p.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        err_console.print("[red]ANTHROPIC_API_KEY is not set.[/] Add it to your environment or a .env file.")
        return 2

    try:
        keys = [k.strip() for k in args.reviewers.split(",")] if args.reviewers else None
        reviewers = select_reviewers(keys)
    except ValueError as exc:
        err_console.print(f"[red]{exc}[/]")
        return 2

    if args.rounds < 0:
        err_console.print("[red]--rounds must be >= 0.[/]")
        return 2

    try:
        with console.status("Loading PDF…"):
            pdf = load_pdf(args.pdf, max_pages=args.max_pages)
    except (FileNotFoundError, ValueError) as exc:
        err_console.print(f"[red]{exc}[/]")
        return 1

    console.print(
        f"[bold]{pdf.filename}[/] · {pdf.n_pages} pages · "
        f"{len(reviewers)} reviewers · {args.rounds} discussion round(s) · {args.model}"
    )

    client = Client(model=args.model)
    result = await run_panel(
        pdf,
        reviewers,
        client=client,
        rounds=args.rounds,
        cache=not args.no_cache,
        on_event=lambda m: console.print(f"[dim]• {m}[/]"),
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(to_json(result), encoding="utf-8")
    if not args.json_only:
        (out_dir / "report.md").write_text(to_markdown(result), encoding="utf-8")

    rec = result.meta_review.get("recommendation", "?")
    console.rule("[bold]Result")
    console.print(f"Recommendation: [bold]{rec}[/]")
    console.print(f"Wrote reports to [bold]{out_dir}/[/]")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
