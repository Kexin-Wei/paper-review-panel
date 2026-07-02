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

Figure judgement is native: the PDF is parsed once (text + one image per page)
and streamed inline to every reviewer, so figures and tables are preserved and
critiqued by number.

It runs on the **Claude Agent SDK** — no API key. Authentication and billing go
through your **Claude Code subscription** via the `claude` CLI.

## Setup

Requires the [Claude Code](https://claude.com/claude-code) CLI installed and
logged in (run `claude` once to authenticate). No `ANTHROPIC_API_KEY` is needed.

### 1. Install the CLI globally

```bash
uv tool install /path/to/paper-review-panel
```

Puts `review-panel` on your `$PATH` so every shell and every coding agent
(Claude Code, opencode, antigravity, plain bash) can invoke it. For local
development instead, use `pip install -e .` inside the repo.

Verify from any directory:

```bash
review-panel --version
```

### 2. Expose it as an agent skill (Claude Code + opencode)

The repo ships a skill at [.claude/skills/paper-review/SKILL.md](.claude/skills/paper-review/SKILL.md).
Symlink it into `~/.claude/skills/` so both Claude Code and opencode auto-discover
it and know **when** to invoke `review-panel` (triggers live in the skill's
frontmatter):

```bash
mkdir -p ~/.claude/skills
ln -sfn "$(pwd)/.claude/skills/paper-review" ~/.claude/skills/paper-review
```

Run this from the repo root. The symlink keeps a single source of truth: edit
the skill in the repo, both agent surfaces see the update.

**Antigravity** (or any agent that doesn't read `~/.claude/skills/`) still
works — it invokes the CLI via its bash tool, no extra setup.

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

Written next to the PDF (or under `./out/` for URL sources), named after the paper:

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
