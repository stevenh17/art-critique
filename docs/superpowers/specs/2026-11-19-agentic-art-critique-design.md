# Agentic Art Critique — Design

Date: 2026-11-19 · Status: draft for Steven's approval

Marks: **(Steven)** = decided by Steven in conversation. **(Claude's call)** = proposed by Claude, not explicitly confirmed; open to change.

## 1. Intent

An app where an artist uploads a drawing plus the reference photo it was drawn from. Agents compare the two and suggest a few specific, located improvements. The artist revises and resubmits; the system checks whether the advice worked. Critique quality improves over time through a shared, curated memory of "lessons", consolidated offline by a single "dreamer" agent (after Anthropic's agent-memory "dreaming" approach).

**Why:** primarily a portfolio project — a well-documented public GitHub repo plus a public portfolio site, showing agentic design, memory consolidation, and evaluation discipline, with lesson changes versioned and revertible (Steven). Secondarily, if it works, open it to real external users; keep the parts separated so that later step is a storage/auth/engine swap, not a redesign (Steven).

**Cost constraint:** free beyond Steven's existing Claude Pro plan — no paid API usage, no paid hosting (Steven).

## 2. Goals, non-goals, anti-goals

Goals
- Beginner/intermediate artists; realistic and semi-realistic drawings (Steven). MVP user: Steven only (Steven).
- Objective, reference-checkable issues: proportions/placement, anatomy, values/shading, edges/detail (Steven).
- The revise-and-resubmit loop is core (Steven).
- Lessons improve from evidence, mainly revision outcomes (Steven).
- Results automatically published to a free static portfolio site (Steven).

Non-goals (MVP)
- Stylized art; subjective critique (composition, mood, style) (Steven).
- Other users, accounts, consent flows, rate limits, deletion requests.
- A hosted, interactive app. The app runs on Steven's laptop; only a static site is public (Steven).
- **The test gate** — deferred as a TODO until test cases exist (Steven). See §12.

Anti-goals
- **Learning to please instead of help** — flattering advice winning on thumbs-up. Outcome signals outweigh ratings (Steven).
- Following instructions typed by users. User text is data (Steven).
- Lessons containing users' images or verbatim text (Steven).
- The critic grading its own homework: the revision judge is a separate call, and geometry overrides it where available (Steven, via option C).

## 3. Constraints

- Python (Steven).
- Runs locally on Steven's laptop (macOS); model calls go through Claude Code under Steven's Pro login, counting against his Pro usage limits (Steven, via the free constraint).
- Lessons are markdown files in git, in the main repo under `lessons/` (Claude's call); each dreamer run opens a PR; Steven reviews each PR; rollback = revert (Steven).
- Single writer for lessons (the dreamer) (Steven).

## 4. Approaches considered

1. **Fixed pipeline everywhere** — critic is one structured vision call; dreamer is a script. Cheapest and most testable, but the critic can't look closer before claiming, and the "agentic" part is thin.
2. **Agents everywhere, full harness** — both critic and dreamer as full Claude Agent SDK agents with file/shell access. Strongest showcase, but the critic's behaviour and usage vary more and are harder to pin down.
3. **Hybrid — chosen (Steven).** The critic is an agent with a small fixed toolbox (only our five tools, all built-in tools disabled) and a step cap. The dreamer is a full agent, because its job — read many logs, edit files, write a PR — is what an agent harness is for, and PR review catches its mistakes.

Engine note: the original hybrid ran the critic on the paid Anthropic API with our own loop. The free constraint moves both agents onto the **Claude Agent SDK authenticated with Steven's Claude login** (Claude's call, following Steven's free constraint). The design is unchanged: the critic still gets only our tools (exposed as in-process custom tools) and `max_turns`; the dreamer gets file tools restricted to `lessons/` plus `gh`. All agent calls go through one `engine` module so switching to the paid API later is a one-module change.

Revision judging, options considered: (A) vision-model judge only — covers everything but self-grading risk; (B) measured geometry only — objective but proportions-only, detectors may fail on sketches; **(C) both, geometry wins where confident — chosen (Steven).**

Deployment, options considered: hosted interactive app (needs paid API or Steven's login on a server — rejected on cost and usage-terms risk); **local app + automatically published static site — chosen (Steven).**

## 5. Architecture

Four separate parts (Claude's call): **critic, session log, dreamer, test gate (TODO)** — plus a local web app, an image/geometry module shared by critic, judge and (later) eval, and a static-site publisher.

```
local web app (FastAPI + Jinja + HTMX, http://localhost)
  ├─ preprocess   (OpenCV: deskew/crop/normalize)
  ├─ critic       (Agent SDK, our 5 tools only, max_turns) ── reads lessons/
  ├─ judge        (separate agent call on resubmission) + geometry
  ├─ session log  (SQLite + images on disk, append-only)
  └─ publisher    (renders static site → pushes to GitHub Pages)
dreamer (Agent SDK, CLI) ── reads session log ── edits lessons/ ── opens PR (gh)
test gate (TODO) ── will score the critic on a held-out set before merges
```

Stack (Claude's calls): FastAPI, Jinja templates, HTMX, a small vanilla-JS canvas component; OpenCV; MediaPipe face landmarker; a background-removal model for photo subject masks (builder picks, e.g. `rembg`); SQLite; images under `data/` (git-ignored); `claude-agent-sdk` for critic, judge and dreamer; `gh` CLI for PRs; GitHub Pages for the site.

Subjects and media (Claude's call): any realistic subject is accepted. Outline geometry assumes dark marks on light paper or a light digital canvas; for toned paper, charcoal-heavy or dark-background drawings it reports "unavailable" and the judge decides alone. Digital drawings skip deskew.

**First spike (must run before building the critic):** confirm the Agent SDK runs on Steven's laptop under his Pro login (no API key), with custom in-process tools, image inputs, built-in tools disabled, and `max_turns` honoured. Fallback if the SDK requires an API key: drive `claude -p` (headless Claude Code) with our tools served as a local MCP server and `--allowedTools` limited to them. Steven should also skim Anthropic's current usage terms for personal, local use of his subscription this way.

Usage limits: each critique is one agent run with several image-bearing turns. If Pro limits are hit, the app shows a clear "usage limit reached, try again later" message and keeps the submission queued rather than failing silently (Claude's call).

## 6. User flow and UI

**Upload (new drawing)**
1. Upload drawing (scan, phone photo of paper, or digital) and reference photo.
2. Drawing is auto-deskewed (detect paper quad, perspective-warp, normalize exposure/white balance). Steven sees the result and can drag the four corners to fix it (Claude's call — a bad deskew silently corrupts every proportion check).
3. Steven crops the reference photo to roughly what he drew (one drag). Required — the overlay alignment needs matching framing.
4. "Publish this drawing" checkbox (default on), plus the reference photo's source link and license (e.g. "Unsplash", "CC BY 4.0 — author name"). Reference photos are freely licensed material (Steven); the source/license fields exist so the site can show attribution, which some free licenses require (Claude's call). See §13.
5. Submit → critique.

**Critique results — layout A "side by side" (Steven, via Claude's recommendation)**
- Drawing and photo side by side (stacked on narrow screens), **2–3 numbered issues** shown as matching numbered boxes on both.
- Issue cards: title and a located, directional instruction ("chin ends ~¼ head-height lower than the photo; shorten from the mouth down"), never vague.
- Per issue: 👍 / 👎 / "Unclear" / "Show me" (zooms both crops side by side; logged as engagement) / **"That was on purpose"**.
- Overlay toggle: drawing faded over the aligned photo, with an opacity slider.

```
[ Your drawing  ①② ] [ Reference ①② ]      (overlay ⟷)
① Jaw too long — chin ~¼ head lower than photo. Shorten from mouth down.
   👍 👎 Unclear  Show me  That was on purpose
② Eye line too high — eyes above halfway; photo has them on it.
[ Upload revision ]
```

**Intentional departures — marked after the critique (Steven, via Claude's recommendation).** "That was on purpose" hides the issue, stores the region as intentional for this drawing so critiques of its revisions skip it, and is logged as its own signal (not a 👎).

**Revision** — "Upload revision" on a drawing's page: new drawing image; same reference and crop reused. Produces (a) outcome verdicts for the previous issues ("① fixed, ② partly") and (b) a fresh critique of the revision.

**Optional click-points** (Claude's call): when a proportion issue can't be measured automatically, the revision page offers "help me measure": click ~5–6 named points (eye corners, nose tip, chin, hairline) on photo and both drawing versions. Skippable.

No login: the app binds to localhost only (Claude's call).

## 7. Critic

An Agent SDK agent with built-in tools disabled:
- **Context:** normalized drawing, cropped photo, core rubric (`lessons/core.md`), the list of topic lessons (name + one-line description), and intentional-departure regions for this drawing.
- **Tools** (our in-process Python functions, read-only):
  - `zoom(image, region)` → higher-res crop of drawing or photo.
  - `grid_overlay(image)` → image with a labeled grid (e.g. 8×8, cells A1…H8).
  - `outline_compare(region?)` → overlay outline distance overall or in a region (from the geometry module).
  - `face_landmarks()` → detected landmarks and derived ratios (eye line / head height, etc.) for both images, or "unavailable" with reason.
  - `load_lesson(topic)` → that topic file's text.
- **Cap:** 8 tool calls (Claude's call), then it must answer.
- **Output** (strict JSON, validated; one retry on invalid): 2–3 issues, ordered big proportions/placement → anatomy → values/shading → edges/detail (Claude's call, from instructor practice). Each: `category`, `title`, `instruction` (what to change and in which direction), `drawing_region`, `photo_region`, `lesson_refs`. Regions are given as grid cells and converted to normalized boxes — vision models place grid cells more reliably than pixel coordinates.
- Critic never writes lessons. The app, not the agent, writes the session log.

## 8. Revision judge (option C)

For each issue from the previous version:
1. **Model judge** — a separate agent call (no tools) that sees only the issue's category/title/instruction, the old and new drawing crops for the region, and the photo crop. It never sees the critic's reasoning or tool trace. Verdict: `fixed | partly | not_fixed | can't_tell`.
2. **Geometry**, when available:
   - **Outline overlay (default):** subject outline from drawing (threshold dark marks) and photo (background-removal mask); best-fit similarity transform (shift/scale/rotate) aligns each drawing version to the photo; outline distance (e.g. symmetric chamfer) overall and in the issue region, old vs new.
   - **Face landmarks (bonus):** MediaPipe on photo and both versions; used only if confident on all three and a sanity check passes.
   - **Click-points**, when provided.
3. **Final verdict:** for proportion/placement issues, confident geometry overrides the judge; otherwise the judge stands. Every judge-vs-geometry disagreement is logged.
4. **Whole-drawing closeness:** overall outline distance, old vs new, stored per revision.

Thresholds for "fixed"/"partly" are left to the builder; start with simple defaults and revisit once the test set exists.

Open risk: whether MediaPipe works on Steven's drawings is unknown; a throwaway spike on 5–10 pairs once he has them decides how much click-points matter. The design works if face landmarks never succeed.

## 9. Session log

SQLite, append-only: rows are inserted, never updated (Claude's call — ratings and other later facts arrive as event rows).

- `drawings` — id, reference photo path, photo source URL + license, photo crop, publish flag, created_at.
- `submissions` — id, drawing_id, version number, parent_submission_id, original + normalized image paths, deskew corners, critique JSON, tool trace, model id (as reported by the SDK), **lessons git SHA used**, created_at.
- `issues` — id, submission_id, fields from critic output.
- `events` — id, issue_id or submission_id, type (`thumb_up`, `thumb_down`, `unclear`, `intentional`, `show_me`, `help_measure`, `publish_toggle`), payload, created_at.
- `outcomes` — id, issue_id, revision submission_id, judge verdict, geometry measurements + source, final verdict, disagreement flag.

Session-log and image storage sit behind small Python interfaces so Postgres/object storage can replace them later.

## 10. Lessons

```
lessons/
  core.md                    # small rubric loaded into every critique (cap ~1,500 words — Claude's call)
  topics/
    faces-proportions.md
    hands.md
    values-shading.md
    figure-proportions.md
    edges.md
```

Each topic file starts with a one-line description (used in the critic's topic list). Each lesson: heading, guidance bullets, an **Evidence** line (session count, fixed-on-revision count, session IDs), and a dated history line:

```markdown
## Check eye line before features
- Beginners often place the eyes too high. Measure where the eye line falls
  on the head in both drawing and photo before commenting on features.
- Evidence: 14 sessions; fixed on revision in 11. [s_0412, s_0419, …]
- Added 2026-11-20, strengthened 2026-12-03
```

Initial lessons: hand-written `core.md` and a few topic files from standard drawing-instruction practice before any dreamer run (Claude's call).

## 11. Dreamer

An Agent SDK agent, run manually as `python -m dreamer run` on the laptop (Claude's call; scheduling can come later).

- **Reads:** sessions since the last merged dreamer run (watermark in `lessons/.dreamer-state.json`), as structured records: issues, lesson_refs, events, outcomes. User free text, if any, appears only inside delimited data blocks; the system prompt says it is never an instruction.
- **Weighs:** outcomes far above ratings; "unclear" → rewrite; "intentional" → the lesson may overreach on semi-realistic work.
- **Proposes:** strengthen, rewrite, merge, or retire lessons; add one only with ≥ 3 supporting sessions (Claude's call). File access restricted to `lessons/`.
- **Safety checks before PR** (deterministic, in code): no long verbatim overlap with any user-typed text (e.g. ≥ 8-word n-gram match); `core.md` within its size cap; markdown structure valid.
- **Then:** creates a branch, commits, opens a PR via `gh` with change summary and reasons, evidence links, and the line **"Not checked by a test gate (TODO)"**. Steven reviews and merges.
- With one user, evidence accumulates slowly; expect early dreamer runs to propose little. That's fine.

## 12. Test gate — TODO (Steven)

Deferred until test cases exist. Until then, lesson PRs are protected only by Steven's review and the deterministic safety checks. Keep the critic callable as `critique(drawing, photo, lessons_dir) -> issues` so an eval runner can be added without touching the app.

Agreed shape for later:
- **Synthetic known-error set:** freely licensed portrait/figure photos turned into drawing-like images by a pencil-sketch filter, then warped with known distortions ("eyes moved 8% up"). Exact ground truth; measures recall of injected proportion errors.
- **Real set:** drawings Steven and friends make from freely licensed references, posted by Steven to a critique forum; human critique points transcribed and matched against the critic's issues.
- **Lean gate (fits Pro limits):** store the last merged lessons' score; run only the new lessons, once, on ~15–20 cases; block if the score drops beyond a tolerance. Eval data stays outside the repo and out of the dreamer's reach; the dreamer would see only the aggregate result.

## 13. Static portfolio site (automatic publishing)

- **What's on it:** a gallery of published drawings, each with its critique, issue boxes, revisions and outcome verdicts ("① fixed on revision 2"); a lessons page rendering `lessons/` with each lesson's history; a short "how it works" page with the architecture and memory loop.
- **When:** automatically after each new critique, revision, or merged lesson PR the app notices on startup (Claude's call). The publisher renders HTML from the session log into `site/` and pushes it to the repo's `gh-pages` branch; GitHub Pages serves it. If the push fails (offline), it retries on the next publish.
- **Reference photos are published** alongside each drawing, with their source link and license shown as attribution (Steven: only freely licensed references are used).
- **What's left out (Claude's calls):** drawings with "Publish this drawing" off; internal fields (tool traces, file paths, raw event logs). Thumbs/clicks appear only as aggregate counts.
- No JavaScript backend; no Claude calls; costs nothing.

## 14. Repo and docs

Public GitHub repo with a portfolio-quality README (what it does, architecture diagram, memory loop, how to run locally, link to the live site, an example dreamer PR). `.gitignore` covers `data/`, `site/`, `.env`, `.superpowers/`.

## 15. Later (designed for, not built)

Paid API engine (swap `engine` module) for a hosted interactive app; accounts and opt-in consent; Postgres + object storage; scheduled, topic-sharded dreamer runs; the test gate and auto-merge on pass; rate limits; deletion requests; defenses against feedback gaming and junk uploads.

## 16. Left to the builder

- Prompts and tool schemas.
- Outline extraction, alignment algorithm, distance metric, verdict thresholds.
- Background-removal library choice.
- Visual design beyond layout A; static-site styling.
- Test framework and project layout details.
- Lesson topics beyond the starting five.

## 17. Open items needing Steven later

- Drawing/photo pairs for the MediaPipe spike and, later, the test set.
- Which critique forum to use (check its terms).
- A quick read of Anthropic's usage terms for running the Agent SDK / `claude -p` on his Pro login locally.
