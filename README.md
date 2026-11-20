# Agentic Art Critique

Upload a realistic drawing and the reference photo you drew it from. An agent compares the two and gives you the **2–3 most important fixes**. Each fix points to the same spot on both images and says what to change and which way ("the chin ends about a quarter head lower than in the photo; shorten from the mouth down").

Critique quality improves over time through a curated memory of **lessons**: markdown files in [`lessons/`](lessons/) that a separate "dreamer" agent consolidates offline from session outcomes, through reviewed pull requests.

> Status: **Plans 1–3 of 4** (critique core, revisions and judging, portfolio site) are built. See the [roadmap](#roadmap).
>
> Live portfolio: *(link appears once GitHub Pages is set up — see [docs/publishing.md](docs/publishing.md))*

## How it works

```
local web app (FastAPI + Jinja + HTMX, http://127.0.0.1:8000)
  ├─ preprocess   OpenCV: find the paper, flatten the phone photo, normalize
  ├─ critic       agent with ONLY five tools (zoom, grid_overlay, load_lesson,
  │                 outline_compare, face_landmarks), ≤ 8 tool calls in total
  │                 └─ reads lessons/core.md + topic lessons on demand
  ├─ geometry     outline extraction + best-fit alignment, MediaPipe face landmarks
  ├─ judge        separate agent call, no tools: was each issue fixed in the revision?
  └─ session log  append-only SQLite + images under data/
  └─ publisher    rebuilds a static site → commits to gh-pages → pushes (GitHub Pages)
dreamer (planned)  reads the log → edits lessons/ → opens a PR for review
```

- **Bounded agent.** The critic runs on the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk) with every built-in tool disabled. It can only zoom into grid cells, overlay a labeled A1–H8 grid, and load a lesson. Output is validated JSON: wrong cells, a wrong issue count, or an unknown category get one retry.
- **Separation of roles.** Critic agents read lessons and never write them. Only the dreamer writes lessons, and every change is a pull request.
- **The critic never grades its own homework.** When you upload a revision, a separate judge sees only the issue and three crops (old, new, photo), never the critic's reasoning. For proportion issues, confident measurement overrides the judge: outline distance after best-fit alignment, face-landmark ratios when the issue is about one or two features, or six points you click ("Help me measure"). Every judge/measurement disagreement is logged.
- **Append-only log.** Ratings, "That was on purpose" and "Show me" clicks are new event rows; nothing is overwritten.
- **Public portfolio, private workshop.** The app runs only on your laptop; a static site of published drawings, critiques, revision outcomes and lesson history is rebuilt and pushed to GitHub Pages automatically. Original phone photos, tool traces and judge reasoning never leave the machine. See [docs/publishing.md](docs/publishing.md).
- **Runs on your Claude login.** No API key; usage counts against your Claude plan. If you hit the limit, the submission waits with a Retry button.

## Run it

Requires Python ≥ 3.11 and a Claude subscription you've signed in to on this machine.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/artcrit fetch-models # one-time: face landmark model (3.8 MB) into data/models/
.venv/bin/artcrit serve        # http://127.0.0.1:8000
```

Tests:

```bash
.venv/bin/pytest                         # unit and web tests (fake engine)
ARTCRIT_LIVE=1 .venv/bin/pytest -m live  # one real critique on your login
```

## Roadmap

1. **Critique core** ✅: upload, deskew, crop, critic, session log, results page.
2. **Revisions and judging** ✅: resubmit a revision; a separate judge plus outline and face-landmark geometry decide whether each issue was fixed; aligned overlay.
3. **Static portfolio site** ✅: automatic publishing of critiques, revisions and lesson history to GitHub Pages, with photo attribution.
4. **Dreamer:** offline lesson consolidation that opens pull requests.
5. *TODO:* **test gate**, a held-out benchmark that blocks lesson changes that make critiques worse.

Design: [`docs/superpowers/specs/2026-11-19-agentic-art-critique-design.md`](docs/superpowers/specs/2026-11-19-agentic-art-critique-design.md).
