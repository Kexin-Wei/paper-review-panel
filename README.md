# review-panel

An **agentic paper review panel**. Point it at a PDF (URL or local file) and it
convenes a committee of Claude reviewers — each with a distinct perspective —
that read the paper **including its figures and tables**, then an Area Chair
synthesises their reviews into an accept / revise / reject recommendation.

It models a real program committee:

1. **Triage** — detect the paper's field so the domain expert adapts to it.
2. **Independent reviews** — every reviewer reviews in parallel, blind to the others.
3. **Discussion round(s)** — reviewers see each other and may revise their scores.
4. **Area Chair** — weighs the reviews, surfaces disagreements, and decides.

Figure judgement is native: each reviewer opens the PDF with Claude Code's `Read`
tool, which renders every page as an image, so reviewers critique specific figures
and tables by number.

It runs on the **Claude Agent SDK** — no API key. Authentication and billing go
through your **Claude Code subscription** via the `claude` CLI.

## Install

```bash
pip install -e .
```

Requires the [Claude Code](https://claude.com/claude-code) CLI installed and logged
in (run `claude` once to authenticate). No `ANTHROPIC_API_KEY` is needed.

## Usage

```bash
review-panel https://arxiv.org/pdf/1706.03762            # from a URL
review-panel ./mypaper.pdf --rounds 0                     # fast single-pass
review-panel ./mypaper.pdf --reviewers methodology,novelty,domain_expert
```

Options:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--rounds N` | `1` | Discussion rounds after the independent pass (`0` = single-pass). |
| `--reviewers a,b` | full roster | Subset of reviewer keys to run. |

Reviewer keys: `methodology`, `novelty`, `clarity`, `domain_expert`,
`reproducibility`, `ethics_impact`, `ai_style`. Edit `src/review_panel/reviewers.yaml` to add,
remove, or re-word reviewers — the panel size adapts automatically.

Other settings are constants (rarely changed, edit in code): the model, page
limit, output directory, and JSON-only mode live in `src/review_panel/config.py`
(`DEFAULT_MODEL`, `DEFAULT_MAX_PAGES`, `DEFAULT_OUT_DIR`, `JSON_ONLY`); the reviewer
concurrency cap is `DEFAULT_CONCURRENCY` in `src/review_panel/panel.py` (defaults
to `8` so the full 7-reviewer roster runs in a single parallel wave per phase —
lower it to `4` or `5` if your subscription tier trips rate limits).

## Output

Written next to the PDF (or under `--out DIR`), named after the paper:

- `<pdf>.review.md` — recommendation, score table, Area Chair meta-review, and each
  full review (summary, strengths, actionable weaknesses, figure assessments,
  questions).
- `<pdf>.review.json` — the same data structured, including each reviewer's
  round-by-round history and token/cache usage.

## Development

```bash
pip install -e ".[dev]"
pytest
```
