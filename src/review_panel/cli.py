"""Command-line entrypoint: ``review-panel <pdf-url-or-path> [flags]``."""

from __future__ import annotations

import argparse
import asyncio
import shutil
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
    JSON_ONLY,
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
    p.add_argument("--version", action="version", version=f"review-panel {__version__}")
    return p.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    if shutil.which("claude") is None:
        err_console.print(
            "[red]The `claude` CLI was not found.[/] The panel runs on your Claude Code "
            "subscription — install Claude Code and run `claude` to log in, then retry."
        )
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
            pdf = load_pdf(args.pdf, max_pages=DEFAULT_MAX_PAGES)
    except (FileNotFoundError, ValueError) as exc:
        err_console.print(f"[red]{exc}[/]")
        return 1

    console.print(
        f"[bold]{pdf.filename}[/] · {pdf.n_pages} pages · "
        f"{len(reviewers)} reviewers · {args.rounds} discussion round(s) · {DEFAULT_MODEL}"
    )

    client = Client(model=DEFAULT_MODEL)
    result = await run_panel(
        pdf,
        reviewers,
        client=client,
        rounds=args.rounds,
        on_event=lambda m: console.print(f"[dim]• {m}[/]"),
    )

    # Write next to the PDF (local file), named after it; else ./out/ (URLs).
    if Path(pdf.path).is_file() and not pdf.source.startswith(("http://", "https://")):
        out_dir = Path(pdf.path).parent
    else:
        out_dir = Path(DEFAULT_OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(pdf.filename).stem or "paper"
    json_path = out_dir / f"{stem}.review.json"
    json_path.write_text(to_json(result), encoding="utf-8")
    written = [json_path]
    if not JSON_ONLY:
        md_path = out_dir / f"{stem}.review.md"
        md_path.write_text(to_markdown(result), encoding="utf-8")
        written.insert(0, md_path)

    rec = result.meta_review.get("recommendation", "?")
    console.rule("[bold]Result")
    console.print(f"Recommendation: [bold]{rec}[/]")
    for path in written:
        console.print(f"Wrote [bold]{path}[/]")
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
