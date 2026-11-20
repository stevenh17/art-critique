# The dreamer

The dreamer is the only thing that changes `lessons/`. It runs offline, on your Claude login, and every change it proposes arrives as a pull request you review and merge (or close).

```bash
.venv/bin/artcrit dream --dry-run    # show the proposed diff; create nothing
.venv/bin/artcrit dream              # create a dreamer/<date>-<time> branch, push it, open a PR
.venv/bin/artcrit dream --no-push    # create the branch locally only
```

`--force` runs even with little evidence or while an earlier dreamer branch is still unmerged. Every run writes a report to `data/dreamer/last-run.md`.

## What it reads

Structured evidence about each critiqued issue since the last **merged** dreamer run: its category, title and instruction, which lessons the critic cited, rating counts, whether you marked it "on purpose", and the revision outcomes (fixed / partly / not fixed, measured or judged). It never sees images, file paths, tool traces, the judge's reasoning, or anything you typed.

An issue critiqued long ago comes back into the evidence when it later gets a revision outcome or new feedback, so slow revisions still count.

It skips the agent entirely when fewer than 3 issues have outcomes or ratings ("nothing to learn yet").

## How it decides

Revision outcomes count far more than ratings: advice that led to real fixes gets strengthened, advice that keeps failing gets rewritten or retired, "unclear" means rewrite the wording, and "on purpose" means the lesson may be overreaching. It adds a new lesson only with at least 3 supporting sessions, and it is told to change nothing when the evidence doesn't clearly support a change.

The agent can only list, read and write lesson files in memory and then call `finish`. It has no file system, shell or web access.

## Safety checks (before any branch exists)

- Every lesson file keeps the format: `# Title`, a description line, and `##` lessons each with one `- Evidence:` line and a dated `- Added/Strengthened/Rewritten/Merged YYYY-MM-DD` line.
- `core.md` stays under 1,500 words.
- Every cited session (`s12`) exists in the evidence or was already cited on `main`: no made-up evidence.
- A new lesson cites at least 3 sessions; an edited seed lesson cites at least one.
- No 8-word overlap with anything a user typed, and no links or images.

If a check fails, the agent gets one retry with the failures; if it still fails, nothing is created and the report lists why.

## Reviewing and merging

The PR body lists each change with its reason and evidence, the evidence range, and the line **"Not checked by a test gate (TODO)"**: until a held-out test set exists, your review is the gate. Read the wording as a drawing teacher would.

- **Merge**: the lessons change for every future critique, the watermark in `lessons/.dreamer-state.json` advances so that evidence isn't reprocessed, and the portfolio site's lessons page republishes the next time `artcrit serve` starts or publishes.
- **Close without merging**: delete the branch (`git branch -D dreamer/…` and on GitHub) so the next run isn't blocked; the same evidence will be considered again.
- **Roll back** a merged change: revert its merge commit.

Without `gh` installed, the run prints a GitHub "open a pull request" link for the pushed branch instead of opening the PR itself.

## A caution about test data

The dreamer learns from whatever is in `data/sessions.db`. Synthetic or test sessions produce lessons about test images; clear them out (or start a fresh `data/`) before relying on dreamer PRs.
