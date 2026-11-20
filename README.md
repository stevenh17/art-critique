# Agentic Art Critique

Upload a realistic drawing and the reference photo you drew it from. An agent compares the two and gives you the **2–3 most important fixes**. Each fix points to the same spot on both images and says what to change and which way ("the chin ends about a quarter head lower than in the photo; shorten from the mouth down").

Critique quality improves over time through a curated memory of **lessons**: markdown files in [`lessons/`](lessons/) that a separate "dreamer" agent consolidates offline from session outcomes, through reviewed pull requests.

> Status: **Plan 1 of 4 (critique core)** is built. See the [roadmap](#roadmap).

## How it works

```
local web app (FastAPI + Jinja + HTMX, http://127.0.0.1:8000)
  ├─ preprocess   OpenCV: find the paper, flatten the phone photo, normalize
  ├─ critic       agent with ONLY three tools (zoom, grid_overlay, load_lesson), ≤ 8 tool calls
  │                 └─ reads lessons/core.md + topic lessons on demand
  └─ session log  append-only SQLite + images under data/
dreamer (planned)  reads the log → edits lessons/ → opens a PR for review
```

- **Bounded agent.** The critic runs on the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk) with every built-in tool disabled. It can only zoom into grid cells, overlay a labeled A1–H8 grid, and load a lesson. Output is validated JSON: wrong cells, a wrong issue count, or an unknown category get one retry.
- **Separation of roles.** Critic agents read lessons and never write them. Only the dreamer writes lessons, and every change is a pull request.
- **Append-only log.** Ratings, "That was on purpose" and "Show me" clicks are new event rows; nothing is overwritten.
- **Runs on your Claude login.** No API key; usage counts against your Claude plan. If you hit the limit, the submission waits with a Retry button.

## Run it

Requires Python ≥ 3.11 and a Claude subscription you've signed in to on this machine.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/artcrit serve        # http://127.0.0.1:8000
```

Tests:

```bash
.venv/bin/pytest                         # unit and web tests (fake engine)
ARTCRIT_LIVE=1 .venv/bin/pytest -m live  # one real critique on your login
```

## Roadmap

1. **Critique core** ✅: upload, deskew, crop, critic, session log, results page.
2. **Revisions and judging:** resubmit a revision; a separate judge plus outline and face-landmark geometry decide whether each issue was fixed.
3. **Static portfolio site:** automatic publishing of critiques, revisions and lesson history to GitHub Pages, with photo attribution.
4. **Dreamer:** offline lesson consolidation that opens pull requests.
5. *TODO:* **test gate**, a held-out benchmark that blocks lesson changes that make critiques worse.

Design: [`docs/superpowers/specs/2026-11-19-agentic-art-critique-design.md`](docs/superpowers/specs/2026-11-19-agentic-art-critique-design.md).
