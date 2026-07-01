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

Figure judgement is native: Claude sees every PDF page as an image, so reviewers
critique specific figures and tables by number. The PDF is attached once and
reused across all calls via prompt caching to keep cost down.

## Install

```bash
pip install -e .
cp .env.example .env      # then put your key in it
```

Requires `ANTHROPIC_API_KEY` (from the environment or a `.env` file).

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
| `--model ID` | `claude-opus-4-8` | Model for all agents. |
| `--out DIR` | `out` | Where `report.md` / `report.json` are written. |
| `--json-only` | off | Skip the Markdown report. |
| `--no-cache` | off | Disable PDF prompt caching. |
| `--max-pages N` | `100` | Reject longer PDFs. |

Reviewer keys: `methodology`, `novelty`, `clarity`, `domain_expert`,
`reproducibility`, `ethics_impact`. Edit `src/review_panel/reviewers.yaml` to add,
remove, or re-word reviewers — the panel size adapts automatically.

## Output

- `out/report.md` — recommendation, score table, Area Chair meta-review, and each
  full review (summary, strengths, actionable weaknesses, figure assessments,
  questions).
- `out/report.json` — the same data structured, including each reviewer's
  round-by-round history and token/cache usage.

## Development

```bash
pip install -e ".[dev]"
pytest
```
