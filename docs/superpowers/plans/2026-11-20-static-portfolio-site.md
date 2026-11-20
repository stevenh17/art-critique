# Static Portfolio Site (Plan 3 of 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After every finished critique or revision, and whenever merged lessons change, the local app rebuilds a static portfolio site and pushes it to the repo's `gh-pages` branch for GitHub Pages to serve. The site is free and has no backend. It shows:
- a gallery of published drawings, each with every version's critique, numbered boxes, outcome verdicts and the reference photo with credit;
- the lessons with their change history;
- a "how it works" page.

**Architecture:** A new `artcrit/site/` package with four parts:
- `model.py` reads the session log into plain, publish-safe data classes; this is the only place that decides what is public;
- `export.py` writes size-bounded JPEGs;
- `render.py` renders Jinja templates to `site/` with relative links only;
- `publish.py` commits `site/` onto `gh-pages` through git plumbing with a temporary index, so Steven's working tree, index and current branch are never touched, then pushes if a remote exists.

A single-flight `Publisher` runs this in the background after the worker finishes and at startup.

**Tech Stack:** As in Plans 1–2, plus `markdown==3.11.3` for the lessons pages. Git plumbing via `subprocess` (git 2.39 is installed). `gh` is not required by the code. Steven creates the GitHub repo and turns on Pages himself (Task 8).

**Spec:** `docs/superpowers/specs/2026-11-19-agentic-art-critique-design.md` §13 (static portfolio site), §6 (publish checkbox, attribution), §9 (`publish_toggle` event), §14 (repo/README).

**Builds on (`main`), exact names:**
- `SessionStore`:
  - `get_submission -> SubmissionView` (fields `id, drawing_id, version, normalized_path, photo_path, photo_crop, photo_source_url, photo_license, publish, status, status_detail, model, lessons_sha, issues, parent_id`)
  - `versions(drawing_id) -> [(submission_id, version)]`
  - `outcomes_for(sid) -> [OutcomeView(issue_id, number, category, title, final_verdict, source, judge_verdict, judge_reason, disagreement)]`
  - `revision_metrics(sid)`, `add_event(type, issue_id, submission_id, payload)`
- `EventType` already includes `publish_toggle`.
- `IssueView`: `id, number, category, title, instruction, drawing_cells, photo_cells, rating, intentional, drawing_box, photo_box`.
- `ImageStore.load(rel)` and `crop` from `artcrit.imaging.regions`.
- `lessons_sha(repo_dir)`, `list_topics`, `load_core`, `load_topic` from `artcrit.lessons`.
- `run_submission(submission_id, store, images, engine, settings, geometry)` in `artcrit/web/worker.py`; `create_app(settings, engine, run_in_background, geometry)`; `Settings(data_dir, lessons_dir, repo_dir)`.

## Global Constraints

- **What's public** (spec §13):
  - Only drawings whose effective publish flag is on. The effective flag is the latest `publish_toggle` event, or else `drawings.publish`.
  - Only versions with status `done`.
  - Reference photos **are** published, always with their source link and license (spec §13, Steven).
- **Never public:** tool traces, file paths under `data/`, model reasoning, raw event rows, judge reasons, original (un-deskewed) phone photos, and anything from `status_detail`. Ratings appear only as per-issue totals (spec §13; "original phone photos stay private" is Claude's call, since they show the room/table).
- **The site is rebuilt from scratch on every publish.** An unpublished drawing disappears on the next publish.
- **All links and asset paths are relative** (GitHub Pages serves under `/<repo>/`). No `href="/…"` or `src="/…"` in output.
- **No JavaScript is required to read the site.** One small optional script powers the overlay slider.
- **Publishing never changes** the working tree, the index, `HEAD`, or the checked-out branch. It writes only `site/` (git-ignored), the `gh-pages` ref and the remote.
- **No paid services.** GitHub Pages only. The local app stays bound to `127.0.0.1`.
- **Publishing is best-effort.** A failure (no remote, offline, rejected push) never fails a critique. It's recorded and retried on the next publish.
- **Published images** are JPEG, quality 85, long side ≤ 1600 px, with content-hashed filenames.

## Review Focus

1. **Unpublishing a drawing that was already public:** the next publish removes its page and images from `gh-pages`. Test in Task 6.
2. **No remote, offline, or push rejected:** the local build still succeeds, the result records why it wasn't pushed, the app keeps working, and the next publish tries again. Test in Task 5.
3. **HTML or script in model-written titles or instructions, or in the license text and source URL:** everything is escaped; source URLs other than http(s) are dropped. Test in Task 3.
4. **The site served under a sub-path** (`https://<user>.github.io/<repo>/`): every link and asset is relative, and every linked file exists in the output. Test in Task 3.
5. **Steven has uncommitted changes or is on another branch while a publish runs:** `git status --porcelain` and `HEAD` are identical before and after. Test in Task 5.

---

### Task 1: Publish-safe site model

**Files:**
- Create: `artcrit/site/__init__.py`, `artcrit/site/model.py`
- Modify: `artcrit/store/sessions.py` (add `published_drawing_ids`, `effective_publish`, `rating_counts`)
- Test: `tests/site/__init__.py`, `tests/site/test_model.py`

**Interfaces:**
- Produces:
  - `SessionStore.effective_publish(drawing_id) -> bool`
  - `SessionStore.published_drawing_ids() -> list[int]` (ascending)
  - `SessionStore.rating_counts(issue_id) -> dict[str, int]` (keys `thumb_up`, `thumb_down`, `unclear`, `show_me`)
  - Dataclasses in `artcrit/site/model.py`, all JSON-serializable apart from image refs:
    - `SiteIssue(number, category, title, instruction, drawing_box, photo_box, intentional, ratings: dict[str, int])`
    - `SiteOutcome(number, title, verdict, measured: bool)`
    - `SiteVersion(version, slug, drawing_image: str, issues: list[SiteIssue], outcomes: list[SiteOutcome], closeness: float | None, lessons_sha: str, model: str)`. `drawing_image` is an `ImageStore` relative path.
    - `SiteDrawing(id, slug, title, photo_image: str, photo_crop, source_url: str | None, license: str, versions: list[SiteVersion])`. `source_url` is `None` unless the scheme is http(s). `title` is `f"Drawing {id}"`.
    - `SiteData(drawings: list[SiteDrawing], generated_at: str, lessons_sha: str)`
  - `build_site_data(store, repo_dir) -> SiteData`
- Slugs: `d{drawing_id}` and `d{drawing_id}-v{version}`.

- [ ] **Step 1:** Write the failing tests against a real temp `SessionStore`:
  - `test_unpublished_drawing_excluded`
  - `test_toggle_event_overrides_flag`: published, then a `publish_toggle {"publish": false}` event excludes it; another `{"publish": true}` includes it again
  - `test_only_done_versions_included`: a failed v2 is absent; v1 is present
  - `test_issues_and_outcomes_carried`: numbers, titles, boxes, verdicts; `measured` is True when the source starts with `geometry`
  - `test_ratings_are_counts_only`: two 👍 and one 👎 give `{"thumb_up": 2, "thumb_down": 1, ...}`
  - `test_no_private_fields`: `json.dumps(dataclasses.asdict(data))` contains none of `tool_trace`, `status_detail`, `judge_reason`, `original`
  - `test_non_http_source_url_dropped`
- [ ] **Step 2:** Run `.venv/bin/pytest tests/site/test_model.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement the store methods and `model.py`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: publish-safe site model`.

### Task 2: Image export

**Files:**
- Create: `artcrit/site/export.py`
- Test: `tests/site/test_export.py`

**Interfaces:**
- Produces:
  - `PUBLISH_MAX_SIDE = 1600`, `JPEG_QUALITY = 85`
  - `export_image(img: np.ndarray, out_dir: Path) -> str`: writes `assets/<blake2b16>.jpg` under `out_dir` and returns that relative path. Same pixels give the same name.
  - `export_site_images(data: SiteData, images: ImageStore, out_dir: Path) -> dict[str, str]`: maps each `ImageStore` ref to its exported path. Photos are exported **cropped** to `photo_crop` (the critic's frame, so photo boxes line up).

- [ ] **Step 1:** Write the failing tests:
  - `test_export_downscales_and_is_jpeg`: a 4000×3000 input comes out with long side 1600 and JPEG magic bytes
  - `test_same_pixels_same_name`
  - `test_photo_exported_cropped`: the exported photo's size matches the crop's aspect ratio
  - `test_mapping_covers_every_ref`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `export.py`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: site image export`.

### Task 3: Renderer and templates

**Files:**
- Create: `artcrit/site/render.py`, `artcrit/site/templates/{base,index,drawing,about}.html`, `artcrit/site/static/{site.css,overlay.js}`
- Test: `tests/site/test_render.py`

**Interfaces:**
- Consumes: Task 1 `SiteData`; Task 2 `export_site_images`.
- Produces: `render_site(data: SiteData, image_map: dict[str, str], lessons_html: str, out_dir: Path) -> list[Path]`. It clears `out_dir` first and writes:
  - `index.html`: a gallery with each drawing's latest version thumbnail, its title and version count
  - `drawings/<slug>.html`: per drawing, every version top to bottom (newest first). Each version shows its drawing and the reference side by side with numbered boxes (absolute-positioned percentages, as in the local app); issue cards (title, instruction, rating totals); "Since vN" outcomes with verdict chips and measured/judged; and the closeness line. The reference credit appears as `Reference: <a href="{source_url}" rel="noopener nofollow">{license}</a>`, or just the license text when `source_url` is `None`.
  - `lessons.html`: the `lessons_html` passed in
  - `about.html`: the architecture and memory loop, adapted from the README
  - `static/site.css`, `static/overlay.js`, and `.nojekyll`
  - Every page's footer: "Generated {generated_at} · lessons {lessons_sha[:7]}"
- Jinja `Environment(autoescape=True)`. Templates take a `root` variable (`""` or `"../"`) for relative links.

- [ ] **Step 1:** Write the failing tests:
  - `test_writes_expected_files`
  - `test_drawing_page_has_boxes_attribution_outcomes`
  - `test_all_links_relative`: the regex `(href|src)="/` doesn't match anywhere (**Review Focus 4**)
  - `test_every_local_link_resolves`: parse every href and src that isn't http(s) or `#`, resolve it against the page, and check the file exists (**Review Focus 4**)
  - `test_script_in_title_and_license_escaped`: `<script>` appears as `&lt;script&gt;`; a `javascript:` source gives no href (**Review Focus 3**)
  - `test_rerender_removes_stale_pages`: render with drawings {1, 2}, then {1}, and `drawings/d2.html` is gone (**Review Focus 1**, local half)
  - `test_footer_has_lessons_sha`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement the renderer and templates. The CSS reuses the local app's tokens, includes a dark-mode `prefers-color-scheme` block, and stacks the two images below 700 px wide.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: static site renderer`.

### Task 4: Lessons page with history

**Files:**
- Create: `artcrit/site/lessons_page.py`
- Modify: `pyproject.toml` (add `markdown==3.11.3`)
- Test: `tests/site/test_lessons_page.py`

**Interfaces:**
- Produces:
  - `LessonHistory(date: str, sha: str, subject: str)`
  - `lesson_history(repo_dir: Path, rel_path: str, limit: int = 20) -> list[LessonHistory]`: `git log --follow --format=%ad%x09%h%x09%s --date=short -- <rel_path>`; `[]` when git or the repo is missing
  - `lessons_html(repo_dir: Path, lessons_dir: Path) -> str`: `core.md`, then each topic (sorted), each rendered with `markdown.markdown(text, extensions=["extra"])`, followed by a "History" list with date, short SHA and commit subject. Raw HTML in the markdown is escaped before rendering.

- [ ] **Step 1:** Write the failing tests:
  - `test_renders_core_and_topics_in_order`
  - `test_history_from_temp_git_repo`: `git init` in tmp, commit twice, and expect two entries, newest first
  - `test_no_repo_gives_empty_history`
  - `test_raw_html_in_markdown_escaped`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Install with `pip install -e '.[dev]'` and implement `lessons_page.py`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: lessons page with change history`.

### Task 5: Git publisher

**Files:**
- Create: `artcrit/site/publish.py`
- Test: `tests/site/test_publish.py`

**Interfaces:**
- Produces:
  - `PublishResult(committed: bool, commit: str | None, pushed: bool, message: str)`
  - `commit_site(site_dir: Path, repo_dir: Path, branch: str = "gh-pages") -> str | None`:
    - writes the tree using a temporary `GIT_INDEX_FILE` and `--work-tree=site_dir` (`git add -A`, then `git write-tree`)
    - parent is the current `refs/heads/<branch>` (if any)
    - `git commit-tree -m "Publish site"`, then `git update-ref`
    - returns `None` when the tree equals the parent's tree (nothing changed)
    - never touches `HEAD`, the real index or the working tree
  - `push_site(repo_dir, branch="gh-pages", remote="origin") -> tuple[bool, str]`:
    - `(False, "no remote 'origin'")` when there's no remote
    - otherwise `git push <remote> <branch>:<branch>` with a 60 s timeout; returns `(ok, stderr tail)`
    - never force-pushes
  - `publish_site(site_dir, repo_dir) -> PublishResult`: commits, and pushes when there's a new commit **or** the last push failed (the last result is stored at `data/site-publish.json`)

- [ ] **Step 1:** Write the failing tests against a temp repo, with a temp bare repo as the remote:
  - `test_first_publish_creates_branch_with_site_files`
  - `test_second_publish_without_changes_makes_no_commit`
  - `test_changed_site_makes_child_commit`
  - `test_working_tree_index_and_head_untouched`: before publishing, add an uncommitted change and check out a feature branch; afterwards `git status --porcelain`, `HEAD` and the branch name are unchanged (**Review Focus 5**)
  - `test_no_remote_reports_not_pushed`
  - `test_push_to_bare_remote`: the remote's `gh-pages` equals the local one
  - `test_failed_push_retried_next_time`: point the remote at a bad path, then fix it, and the next publish pushes even with no new commit (**Review Focus 2**)
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `publish.py`. All git calls go through one `_git(repo_dir, *args, env=None)` helper (with `check` and captured output); author and committer are the repo's configured identity, with a fallback of `-c user.name=artcrit -c user.email=artcrit@localhost` when none is set.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: gh-pages publisher via git plumbing`.

### Task 6: Publisher service, triggers and CLI

**Files:**
- Create: `artcrit/site/service.py`
- Modify: `artcrit/web/worker.py`, `artcrit/web/app.py`, `artcrit/cli.py`, `artcrit/config.py`, `artcrit/web/templates/base.html`; `tests/web/conftest.py` and the other test files that build `Settings` (pass `publish_enabled=False`)
- Test: `tests/site/test_service.py`, `tests/web/test_publish_triggers.py`

**Interfaces:**
- Produces:
  - `Settings.site_dir -> Path` (`repo_dir / "site"`); `Settings.publish_enabled: bool = True`, set from the env var `ARTCRIT_PUBLISH` (`"0"` disables it); tests construct `Settings` with `publish_enabled=False` unless they're testing publishing
  - `build(store, images, settings) -> Path`: model → export → lessons → render into `settings.site_dir`
  - `Publisher(store, images, settings, run_in_background)`:
    - `request()` is single-flight: at most one build/publish runs at a time, and requests that arrive meanwhile collapse into one follow-up run
    - `last() -> PublishResult | None`
  - `run_submission(..., publisher: Publisher | None = None)` calls `publisher.request()` after a `done` status
  - `create_app(..., publisher: Publisher | None = None)`:
    - builds a default `Publisher` when it's `None` and `settings.publish_enabled`
    - on startup, calls `request()` when the published lessons SHA (in `data/site-publish.json`) ≠ `lessons_sha(repo_dir)`
  - `base.html` footer (local app only): "Portfolio: last published <time> — pushed / not pushed (<message>)"
  - CLI: `artcrit publish` builds and publishes synchronously, then prints the `PublishResult`

- [ ] **Step 1:** Write the failing tests:
  - `test_single_flight_collapses_requests`: 5 requests while one is running lead to exactly 2 runs
  - `test_publish_failure_never_raises`
  - `test_done_submission_triggers_publish`
  - `test_failed_submission_does_not_publish`
  - `test_startup_publishes_when_lessons_changed`
  - `test_unpublish_removes_from_branch` (**Review Focus 1**): publish, record a `publish_toggle` false event, publish again, and the `gh-pages` tree no longer has `drawings/d1.html`
  - `test_footer_shows_last_publish`
  - `test_cli_publish_parses`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement the service, wiring and footer above.
- [ ] **Step 4:** Run `.venv/bin/pytest -q`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: automatic publishing after critiques and lesson changes`.

### Task 7: Per-drawing publish toggle in the app

**Files:**
- Modify: `artcrit/web/app.py`, `artcrit/web/templates/submission.html`
- Test: `tests/web/test_publish_toggle.py`

**Interfaces:**
- Produces:
  - `POST /drawings/{drawing_id}/publish`: form `publish=on|off`; records `publish_toggle {"publish": bool}`; calls `publisher.request()`; redirects back to `Referer` or the latest submission
  - `submission.html` shows "Published on portfolio" or "Not published" from `store.effective_publish`, with a toggle button

- [ ] **Step 1:** Write the failing tests:
  - `test_toggle_records_event_and_flips_effective_flag`
  - `test_toggle_requests_publish`
  - `test_toggle_unknown_drawing_404`
  - `test_page_shows_publish_state`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement the route and template change.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: publish toggle per drawing`.

### Task 8: Go live (local check, then Steven's steps) and README

**Files:**
- Modify: `README.md` (live-site link placeholder, roadmap Plan 3 ✅, a "Publishing" section)
- Create: `docs/publishing.md` (Steven's one-time setup)

- [ ] **Step 1:** Run `ARTCRIT_PUBLISH=0 .venv/bin/artcrit publish`. Then serve `site/` locally (add a `site-preview` config to `.claude/launch.json` running `python -m http.server` in `site/` on port 8010). Open the preview and check: the gallery, a drawing page with v1–v3, the reference credit, boxes, outcome chips, the lessons page with history, dark mode, and the narrow-width stacking.
- [ ] **Step 2:** Write `docs/publishing.md` covering Steven's one-time setup:
  1. Create a public GitHub repo (e.g. `art-critique`).
  2. `git remote add origin …`, then `git push -u origin main`.
  3. Run `artcrit publish`.
  4. In the repo's Settings → Pages, set the source to the `gh-pages` branch, `/` root.
  5. The site appears at `https://<user>.github.io/art-critique/`.
- [ ] **Step 3:** **Stop and ask Steven** before any push: show him what will be public (the drawings list from `published_drawing_ids` and the reference credits). Pushing to a public remote is his call.
- [ ] **Step 4:** Run `.venv/bin/pytest -q`. Expected: all pass.
- [ ] **Step 5:** Commit: `docs: publishing setup and README`.
