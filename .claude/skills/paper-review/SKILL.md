---
name: paper-review
description: MUST USE when the user asks to review, critique, peer-review, or run a full committee review over an academic paper (PDF path or arxiv URL). Invokes `review-panel <pdf>` — a 7-agent Claude committee (methodology, novelty, clarity, domain expert, reproducibility, ethics, AI-style) with a discussion round and Area Chair, with figure-aware reading of every page. Triggers - 'review paper', 'peer review', 'critique paper', 'PDF review', 'arxiv review', 'academic review', 'review this paper', 'run the panel', '리뷰 패널', '논문 리뷰'.
---

# Paper Review Panel

Multi-reviewer Claude committee over a PDF. Reads text **and** page images
(figures/tables preserved), holds a discussion round, then an Area Chair issues
`accept` / `minor_revision` / `major_revision` / `reject`.

## Invocation

The CLI is installed globally as `review-panel` (via `uv tool install`). Run it
directly — no `cd` into the repo needed.

```bash
review-panel <path-or-url>                                    # full: 7 reviewers + 1 discussion + AC
review-panel <path-or-url> --rounds 0                         # single-pass, ~half the time
review-panel <path-or-url> --reviewers methodology,novelty    # subset of the roster
review-panel https://arxiv.org/pdf/1706.03762                 # URL source
```

Reviewer keys: `methodology`, `novelty`, `clarity`, `domain_expert`,
`reproducibility`, `ethics_impact`, `ai_style`.

## Output

Two files, written next to the source PDF (or under `./out/` when the source is
a URL):

- `<stem>.review.md` — recommendation, score table, Area Chair meta-review, full reviews
- `<stem>.review.json` — structured, with per-reviewer round-by-round history and token usage

Always show the user the exact paths after a run.

## Runtime

- Uses the Claude Code subscription via the `claude` CLI. No `ANTHROPIC_API_KEY` required.
- Full 7-reviewer + 1 discussion round on a short paper: ~4–5 min at the current default concurrency (8).
- Requires **bash** permission to invoke the CLI.

## Tuning (constants inside the repo, no CLI flags)

- `DEFAULT_MODEL` (`config.py`) — e.g. `claude-opus-4-8`
- `DEFAULT_ROUNDS` (`config.py`) — discussion rounds after the independent pass (default 1)
- `DEFAULT_MAX_PAGES` (`config.py`) — page ceiling (default 100)
- `DEFAULT_CONCURRENCY` (`panel.py`) — 8; lower to 4–5 if your subscription tier trips rate limits

## When NOT to use

- Single-question queries about a paper (e.g. "summarize the abstract") — use the `read` tool on the PDF instead.
- Non-academic PDFs (contracts, invoices, product manuals).
- Chat-style discussion with one reviewer — this skill always runs a full committee.

## Failure modes

- **`claude` CLI not found / not logged in** → the tool exits with a red hint. Tell the user to install Claude Code and run `claude` once to authenticate.
- **Rate-limit hit on `c=8`** → the client retries 5× with backoff 8→16→32→64s. If it still fails, lower `DEFAULT_CONCURRENCY` in `panel.py` to 4–5.
- **PDF over 100 pages or 32 MB** → the loader refuses; raise the limits in `config.py` if you actually want to review it.
