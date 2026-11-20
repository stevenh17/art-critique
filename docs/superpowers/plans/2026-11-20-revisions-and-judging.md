# Revisions and Judging (Plan 2 of 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Steven can upload a revision of a drawing. For each issue raised last time, the app decides whether it was fixed: a separate judge decides, but measured geometry overrides it for proportion issues when the geometry is confident. The app shows the outcome, measures how much closer the whole drawing got to the reference, and critiques the revision fresh. The critic gains the two geometry tools, and the overlay becomes a properly aligned one.

**Architecture:** A new `artcrit/geometry/` package of pure functions:
- extract outlines from drawing and photo;
- find the best-fit similarity transform (shift, scale, rotation) between them;
- measure the distance between outlines, overall and inside a region;
- detect face landmarks (MediaPipe), with ratios and a sanity check;
- compare artist-clicked points.

A `Geometry` service caches one comparison per drawing/photo pair. Both the critic's new tools and the revision outcome logic use it. The judge is a separate agent call with no tools. `outcomes.py` combines the judge and geometry results into a final verdict. Everything new is written to the append-only log.

**Tech Stack:** As in Plan 1, plus `mediapipe==1.2.3` (prebuilt macOS arm64 package confirmed available) and its `face_landmarker.task` model (3.8 MB, fetched by `artcrit fetch-models`). Photo subject masks use OpenCV GrabCut, so no extra model is needed.

**Spec:** `docs/superpowers/specs/2026-11-19-agentic-art-critique-design.md` (§6 Revision, §7 tools, §8 judge, §9 outcomes)

**Builds on (Plan 1, on `main`), exact names:**
- `SessionStore`: `add_drawing`, `add_submission(drawing_id, version, parent_id, original_path, normalized_path, corners)`, `add_status`, `add_critique`, `add_event`, `get_issue`, `get_submission -> SubmissionView`, `intentional_boxes`, `unfinished_submissions`.
- `SubmissionView` fields: `id, drawing_id, version, normalized_path, photo_path, photo_crop, photo_source_url, photo_license, publish, status, status_detail, model, lessons_sha, issues`.
- `IssueView` fields: `id, number, category, title, instruction, drawing_cells, photo_cells, rating, intentional`, plus the properties `drawing_box` and `photo_box`.
- `critique(drawing, photo, lessons_dir, engine, intentional=None, repo_dir=None) -> CritiqueRun`. In `artcrit/critic.py`: `_make_tools(images, lessons_dir)`, `_budgeted`, `MAX_TOOL_CALLS = 8`, `MAX_TURNS = 12`, `BUDGET_USED`.
- Engine: `AgentEngine.run(system, prompt_text, images, tools, max_turns) -> AgentResult(text, tool_trace, model)`; `ToolSpec`; tool blocks are `{"type": "text", "text"}` or `{"type": "image", "png_b64"}`; errors are `UsageLimitError` and `EngineError`.
- `artcrit/imaging/regions.py`: `Box`, `cells_to_box`, `crop`, `zoom`, `fit`, `model_png_b64`.
- `artcrit/web/worker.py`: `run_critique(submission_id, store, images, engine, settings)`, `FAILED_MESSAGE`, `LIMIT_MESSAGE`.
- `artcrit/web/app.py`: upload meta JSON keys `drawing, photo, corners, photo_source_url, photo_license, publish`. Routes: `/uploads`, `/uploads/{token}/adjust`, `/uploads/{token}/submit`, `/submissions/{id}`, `/submissions/{id}/status`, `/submissions/{id}/retry`, `/submissions/{id}/photo-crop`, `/issues/{id}/events`, `/images/{path}`.
- Tests use `FakeEngine(script)` and `tests/web/conftest.py` (`make_client`, `upload`, `submit`, `answer`, `png_bytes`).

## Global Constraints

- **Verdicts** are exactly `fixed | partly | not_fixed | cant_tell` (spec §8, where it's written "can't_tell").
- **The judge never sees the critic's reasoning or tool trace.** It gets only the issue's `category`, `title` and `instruction`, plus three crops: old drawing, new drawing, photo (spec §8).
- **Geometry overrides the judge only for `category == "proportion"`** and only when it is confident. Every disagreement between judge and geometry is logged (spec §8).
- **Face landmarks** count only when detection is confident on the photo *and* both drawing versions *and* the sanity check passes (spec §8).
- **Outline geometry** reports "unavailable" for dark, toned or charcoal-heavy drawings: a median luminance below 140 on the normalized drawing (spec §5).
- **Intentional issues** are never judged and never shown in outcomes (spec §6).
- **The log stays append-only.** `test_no_update_or_delete_sql` must keep passing. A recomputed outcome is a new row, and the latest row per issue wins (spec §9).
- **The critic's 8-call budget is shared across all five tools** (spec §7).
- **No paid API**, and the app binds to `127.0.0.1` only (spec §3, §6).
- **Starting thresholds** (spec §8 leaves them to the builder; they are constants in `artcrit/outcomes.py`):
  - `FIXED_RATIO = 0.6`, `PARTLY_RATIO = 0.85`
  - `NOISE_FLOOR = 0.015`: an issue region whose old distance is at or below this, as a fraction of subject size, isn't measurable
  - `LANDMARK_FIXED = 0.5`, `LANDMARK_PARTLY = 0.8`

## Review Focus

1. **The revision is photographed at a different distance, angle or position than v1.** Each version is aligned to the photo independently, so the same drawing photographed differently must give nearly the same distances. Test in Task 1.
2. **Stray marks away from the subject** (a signature, a note, construction lines at the page edge): outline extraction keeps the subject. A small far-away blob must not change the subject outline. Test in Task 1.
3. **A previous issue marked "That was on purpose":** it gets no judge call, no outcome row, and no outcome badge. Test in Task 6.
4. **The judge returns garbage, or the engine fails, during a revision:** garbage becomes `cant_tell`. A usage limit puts the whole submission in `limit`, and Retry reruns outcomes and critique without showing duplicates. Tests in Tasks 6 and 7.
5. **A revision uploaded while the previous version has no issues** (it failed, is still running, or hit the limit): there are no outcomes, the page says "Nothing to compare yet", and the fresh critique still runs. Test in Task 7.

---

### Task 1: Outlines, alignment and outline distance

**Files:**
- Create: `artcrit/geometry/__init__.py`, `artcrit/geometry/outline.py`
- Test: `tests/geometry/__init__.py`, `tests/geometry/test_outline.py`

**Interfaces:**
- Produces:
  - `MIN_DRAWING_LUMINANCE = 140`
  - `drawing_media_ok(img) -> bool`: median gray of the normalized drawing is ≥ 140
  - `drawing_mask(img) -> np.ndarray | None`: bool mask of the subject silhouette. Steps: Otsu threshold on dark marks; morphological close with kernel ≈ 2% of the long side; fill external contours; keep the largest component plus any component ≥ 15% of its area. Returns `None` if the mask is < 2% or > 95% of the image.
  - `photo_mask(img) -> np.ndarray | None`: GrabCut, initialized with the rectangle inset 4% from the crop edges, 5 iterations; `None` under the same bounds
  - `contour_points(mask, n: int = 400) -> np.ndarray`: (n, 2) float points evenly spaced along the largest outer contour, in pixels
  - `Similarity(scale: float, angle_deg: float, tx: float, ty: float)` (dataclass): `apply(pts) -> pts`; `matrix() -> 2×3 np.ndarray`
  - `align(src_pts, dst_pts) -> Similarity`: maps src onto dst. Initialize from centroids, the square root of the area ratio, and the principal-axis angle (trying both the angle and the angle + 180°); then up to 30 ICP iterations using nearest neighbours (`scipy` is not allowed; use a `cv2.flann` or brute-force NumPy KD search) with `cv2.estimateAffinePartial2D`; stop when the change is < 1e-3. Return the transform with the lower mean error.
  - `subject_size(pts) -> float`: square root of the contour's polygon area
  - `outline_distance(a_pts, b_pts, size: float, region: np.ndarray | None = None) -> float`: symmetric mean nearest-neighbour distance divided by `size`. When `region` is given (a bool mask over `a_pts`), only `a` points inside it and `b` points within the region's bounding box (padded by 5% of size) count.

- [ ] **Step 1:** Write the failing tests:
  - `test_media_ok_light_paper_true_dark_paper_false`: a white drawing returns True; a mid-grey (110) one returns False
  - `test_drawing_mask_fills_outlined_ellipse`: a 3 px ellipse outline gives a mask whose area is within 10% of the filled ellipse
  - `test_stray_far_blob_ignored`: adding a 20×10 blob in a corner changes mask area by < 1%
  - `test_drawing_mask_none_on_blank`
  - `test_photo_mask_finds_dark_subject_on_light_background`: IoU with the true ellipse > 0.8
  - `test_align_recovers_known_similarity`: contour points of an ellipse with a bump, transformed by (scale 1.3, angle 12°, tx 40, ty −25), give back scale within 3%, angle within 2° and translation within 3 px
  - `test_distance_zero_for_identical_and_positive_for_stretched`: identical gives < 0.005; stretched 15% vertically gives > 0.03
  - `test_distance_invariant_to_how_drawing_was_photographed`: the same subject at 0.7× scale and shifted, after `align` to a reference, gives a distance within 0.005 of the unshifted version (**Review Focus 1**)
  - `test_region_distance_isolates_bottom`: stretching only the bottom 30% raises the region distance for the bottom box well above the top box's
- [ ] **Step 2:** Run `.venv/bin/pytest tests/geometry/test_outline.py -q`. Expected: FAIL (module not found).
- [ ] **Step 3:** Implement `artcrit/geometry/outline.py` as specified.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: outline extraction, similarity alignment, outline distance`.

### Task 2: Face landmarks

**Files:**
- Create: `artcrit/geometry/landmarks.py`
- Modify: `artcrit/cli.py` (add the `fetch-models` subcommand), `pyproject.toml` (add `mediapipe==1.2.3`), `.gitignore` (add `*.egg-info/`, and untrack `artcrit.egg-info`)
- Test: `tests/geometry/test_landmarks.py`

**Interfaces:**
- Produces:
  - `MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"`
  - `model_path(settings) -> Path`: `data/models/face_landmarker.task`
  - `fetch_model(settings) -> Path`: downloads the model if it's missing
  - `FaceLandmarks(points: np.ndarray)`: an (N, 2) array normalized to [0, 1], using MediaPipe's 478-point indices
  - `detect_face(img, model: Path) -> FaceLandmarks | None`: returns `None` if the model file is missing, there's no face, or MediaPipe raises an error. Never crashes.
  - `IDX`: a dict of named indices (`forehead: 10`, `chin: 152`, `l_eye_outer: 33`, `l_eye_inner: 133`, `r_eye_inner: 362`, `r_eye_outer: 263`, `nose_tip: 1`, `nose_base: 2`, `mouth_top: 13`, `mouth_bottom: 14`, `l_brow: 105`, `r_brow: 334`)
  - `face_ratios(lm) -> dict[str, float]`, each measured along the forehead→chin axis:
    - `eye_line`: eye-centre height between forehead (0) and chin (1)
    - `nose_base`, `mouth`, `brow`: the same measure for those features
    - `eye_gap_over_eye_width`
  - `landmarks_sane(lm) -> bool`: going down the axis, brow < eyes < nose base < mouth < chin; the eyes are left/right of the midline; the face height is > 10% of the image
  - `landmark_error(drawing: FaceLandmarks, photo: FaceLandmarks) -> dict[str, float]`: absolute differences of `face_ratios`
- CLI: `artcrit fetch-models` calls `fetch_model(Settings())` and prints the path.

- [ ] **Step 1:** Write the failing tests:
  - `test_ratios_on_synthetic_points`: build a 478×2 array with only the indexed points set to a known face; check `eye_line` ≈ 0.45 and `mouth` ≈ 0.78
  - `test_sanity_rejects_eyes_below_nose`
  - `test_landmark_error_zero_for_same`
  - `test_detect_face_returns_none_without_model`: a `tmp_path` model path that doesn't exist returns `None`
  - `test_detect_face_returns_none_on_blank_image`: mark `@pytest.mark.models`, skipped unless the model file exists
  - `test_fetch_models_subcommand_parses`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Run `.venv/bin/pip install -e '.[dev]'` after the dependency change, implement the module, then run `artcrit fetch-models` once. Register the `models` marker in `pyproject.toml`.
- [ ] **Step 4:** Run `.venv/bin/pytest tests/geometry -q -m "not live"`. Expected: PASS, including the `models` test now that the model is present.
- [ ] **Step 5:** Commit: `feat: face landmarks, ratios and sanity check`.

### Task 3: Geometry service and the critic's two new tools

**Files:**
- Create: `artcrit/geometry/service.py`
- Modify: `artcrit/critic.py`
- Test: `tests/geometry/test_service.py`, `tests/test_critic.py` (tool-name test), `tests/test_critic_geometry.py`

**Interfaces:**
- Consumes: Tasks 1 and 2; Plan 1's `_make_tools` and `_budgeted`.
- Produces:
  - `Comparison(available: bool, reason: str, sim: Similarity | None, drawing_pts, photo_pts_in_drawing, size: float, drawing_shape)`
    - `region_distance(box: Box) -> float | None`: `None` when the region holds fewer than 10 drawing points
    - `overall: float`
  - `FaceComparison(available: bool, reason: str, drawing: FaceLandmarks | None, photo: FaceLandmarks | None, error: dict[str, float])`
  - `Geometry(model_path: Path | None, detector=detect_face)`:
    - `compare(drawing, photo) -> Comparison`: unavailable with a reason (`"drawing media too dark"`, `"no subject outline in drawing"`, `"no subject in photo"`) instead of raising. The photo outline is mapped into drawing pixels via `align(photo_pts, drawing_pts)`.
    - `faces(drawing, photo) -> FaceComparison`
    - Results are cached per `(id(drawing), id(photo))` for the life of the object.
  - `critique(..., geometry: Geometry | None = None)`. When it's `None`, the two tools reply "geometry unavailable".
  - New tools in `_make_tools`, both counted against the shared budget:
    - `outline_compare(cells?: list[str])`: text with the overall distance, the region distance (when cells are given), and scale and rotation; plus one image of the photo outline drawn over the drawing (red over the drawing's black)
    - `face_landmarks()`: text listing each ratio for drawing vs photo and their difference, or "unavailable: <reason>"

- [ ] **Step 1:** Write the failing tests:
  - `test_compare_available_on_light_drawing`
  - `test_compare_unavailable_on_dark_drawing_with_reason`
  - `test_region_distance_none_for_empty_region`
  - `test_cached_once`: the detector is called once across two `faces()` calls
  - in `tests/test_critic.py`, change `test_tools_offered_are_exactly` to the five names `{zoom, grid_overlay, load_lesson, outline_compare, face_landmarks}`
  - `test_outline_compare_tool_text_and_image`
  - `test_face_tool_unavailable_message`: the injected detector returns `None`
  - `test_geometry_tools_share_budget`: 8 calls mixed across tools, then the 9th returns `BUDGET_USED`
- [ ] **Step 2:** Run `.venv/bin/pytest tests/geometry/test_service.py tests/test_critic.py tests/test_critic_geometry.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement `service.py` and extend `_make_tools(images, lessons_dir, geometry)`. Update `_system_prompt` to describe the two tools: outline_compare measures silhouette mismatch; face_landmarks compares facial proportions; both can be unavailable.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: geometry service and critic geometry tools`.

### Task 4: Revision upload

**Files:**
- Modify: `artcrit/store/sessions.py`, `artcrit/web/app.py`, `artcrit/web/templates/submission.html`
- Create: `artcrit/web/templates/revise.html`
- Test: `tests/web/test_revision_upload.py`, `tests/store/test_sessions.py`

**Interfaces:**
- Produces:
  - `SessionStore.latest_submission(drawing_id) -> int | None`
  - `SessionStore.versions(drawing_id) -> list[tuple[int, int]]`: (submission_id, version), ascending
  - `SubmissionView.parent_id: int | None` (new field; read from `submissions.parent_id`)
  - Routes:
    - `GET /drawings/{drawing_id}/revise`: form with one `drawing` file input
    - `POST /drawings/{drawing_id}/revisions`: loads the image, detects corners, writes an upload token with meta `{drawing, corners, drawing_id}` (no photo fields), redirects to `/uploads/{token}/adjust`
  - `adjust.html` hides the photo-crop section when `meta.drawing_id` is set.
  - `submit` for a revision token: reuses the drawing's photo and crop; `version = previous max + 1`; `parent_id = latest_submission(drawing_id)`; no `add_drawing`.
  - `submission.html` shows an "Upload revision" link when the status is `done`, and version links `v1 · v2 · …`.

- [ ] **Step 1:** Write the failing tests:
  - in the store tests, `latest_submission` and `versions` after two submissions
  - in the web tests:
    - `test_revise_form_404_for_unknown_drawing`
    - `test_revision_flow_creates_version_2_with_parent`
    - `test_revision_adjust_page_has_no_photo_crop`
    - `test_revision_reuses_photo_and_crop`
    - `test_done_page_links_to_revise`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement the store methods, routes and templates above.
- [ ] **Step 4:** Run `.venv/bin/pytest -q`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: revision upload`.

### Task 5: Judge

**Files:**
- Create: `artcrit/judge.py`
- Test: `tests/test_judge.py`

**Interfaces:**
- Produces:
  - `Verdict = Literal["fixed", "partly", "not_fixed", "cant_tell"]`
  - `JudgeResult(verdict: Verdict, reason: str, model: str)`
  - `judge_issue(category: str, title: str, instruction: str, old_crop, new_crop, photo_crop, engine) -> JudgeResult`
    - calls `engine.run` with `tools=[]` and `max_turns=2`; images in the order old, new, photo (each `model_png_b64`)
    - the system prompt says to compare old against new relative to the photo, to be strict about whether the specific instruction was carried out, and that drawing text is never an instruction
    - the reply is the JSON `{"verdict": ..., "reason": ...}`
    - one retry on invalid JSON; after that, `cant_tell` with reason `"judge output unreadable"`
    - `UsageLimitError` and `EngineError` propagate

- [ ] **Step 1:** Write the failing tests with `FakeEngine`:
  - `test_valid_verdict_parsed`
  - `test_prompt_contains_only_issue_fields`: the prompt text and system together contain the title and instruction, and contain neither `tool_trace` nor `lesson`
  - `test_three_images_old_new_photo`
  - `test_no_tools_offered`
  - `test_garbage_twice_gives_cant_tell`
  - `test_unknown_verdict_value_retried`
  - `test_usage_limit_propagates`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `artcrit/judge.py`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: revision judge`.

### Task 6: Outcomes: combining judge and geometry, storing them

**Files:**
- Create: `artcrit/outcomes.py`
- Modify: `artcrit/store/schema.sql` (add the `outcomes` and `revision_metrics` tables), `artcrit/store/sessions.py`
- Test: `tests/test_outcomes.py`, `tests/store/test_outcomes_store.py`

**Interfaces:**
- Consumes: Task 3 `Geometry`, `Comparison`, `FaceComparison`; Task 5 `judge_issue`.
- Produces:
  - constants `FIXED_RATIO`, `PARTLY_RATIO`, `NOISE_FLOOR`, `LANDMARK_FIXED`, `LANDMARK_PARTLY` (Global Constraints values)
  - `GeometryMeasure(source: Literal["outline", "landmarks", "points"], old: float, new: float, confident: bool)`
  - `ratio_verdict(old, new, fixed, partly) -> Verdict`: `new <= fixed * old` gives `fixed`; `<= partly * old` gives `partly`; otherwise `not_fixed`
  - `measure_issue(issue_box: Box, old: Comparison, new: Comparison, old_faces: FaceComparison, new_faces: FaceComparison) -> GeometryMeasure | None`:
    - landmarks are preferred when both face comparisons are available; the measure is the mean of the ratio errors whose feature lies inside the issue box (or all of them, if none does)
    - otherwise the outline region distance is used; it's confident only when both are available and `old > NOISE_FLOOR`
  - `final_verdict(category, judge: JudgeResult, geo: GeometryMeasure | None) -> tuple[Verdict, str, bool]`: returns (verdict, source, disagreement)
    - source is `"geometry:<source>"` when it overrides, else `"judge"`
    - disagreement is True when a confident geometry verdict ≠ the judge verdict, for any category; it's logged even when the category isn't `proportion`
  - `evaluate_revision(prev: SubmissionView, new: SubmissionView, images: ImageStore, engine, geometry) -> RevisionResult(outcomes: list[OutcomeRow], overall_old: float | None, overall_new: float | None)`:
    - skips intentional issues (**Review Focus 3**)
    - a judge's `cant_tell` from garbage is kept; `UsageLimitError` propagates
  - `OutcomeRow(issue_id, revision_submission_id, judge_verdict, judge_reason, geometry_json, final_verdict, source, disagreement)`
  - Store:
    - `add_outcome(row: OutcomeRow) -> int`
    - `add_revision_metrics(submission_id, overall_old, overall_new)`
    - `outcomes_for(revision_submission_id) -> list[OutcomeView]` (latest row per `issue_id`, joined to the issue's `number` and `title`)
    - `revision_metrics(submission_id) -> tuple[float | None, float | None] | None` (latest)

- [ ] **Step 1:** Write the failing tests:
  - `test_ratio_verdict_thresholds`: (1.0, 0.5) gives fixed; (1.0, 0.8) gives partly; (1.0, 0.9) gives not_fixed
  - `test_geometry_overrides_only_proportion`
  - `test_disagreement_flagged_even_without_override`
  - `test_not_confident_geometry_never_overrides`
  - `test_noise_floor_makes_unmeasurable`
  - `test_landmarks_preferred_over_outline_when_available`
  - `test_intentional_issue_skipped_no_judge_call` (**Review Focus 3**)
  - `test_garbage_judge_gives_cant_tell_row` (**Review Focus 4**)
  - in the store tests: `test_outcomes_latest_row_per_issue_wins` and `test_revision_metrics_roundtrip`
  - `test_no_update_or_delete_sql` still passes
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `outcomes.py` and the store changes.
- [ ] **Step 4:** Run `.venv/bin/pytest -q`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: outcome verdicts from judge and geometry`.

### Task 7: Worker and revision results page

**Files:**
- Modify: `artcrit/web/worker.py`, `artcrit/web/app.py`, `artcrit/cli.py`, `artcrit/web/templates/submission.html`, `artcrit/web/static/app.css`
- Create: `artcrit/web/templates/_outcomes.html`
- Test: `tests/web/test_revision_results.py`, `tests/web/test_worker.py`

**Interfaces:**
- Produces:
  - `run_submission(submission_id, store, images, engine, settings, geometry)` replaces `run_critique` (keep `run_critique` as an alias for the existing tests).
    - Order: if `parent_id` is set and the parent has non-intentional issues, run `evaluate_revision` and store the outcomes and metrics; then run `critique(..., geometry=geometry)`.
    - The same exception mapping as Plan 1 applies to both steps.
  - `create_app(settings, engine, run_in_background=_thread, geometry: Geometry | None = None)`. The CLI passes `Geometry(model_path(settings))`.
  - `_outcomes.html`:
    - "Since v{{prev.version}}": one row per outcome, with the number badge, title, a verdict chip (`fixed` green / `partly` amber / `not_fixed` red / `cant_tell` grey), and "measured" or "judged" taken from the source
    - one line about overall closeness, e.g. "Outline 18% closer to the reference", computed as `1 - new/old`; shown only when both values are present
    - "Nothing to compare yet" when the parent has no issues
    - placed above the fresh critique

- [ ] **Step 1:** Write the failing tests, using `FakeEngine` scripts (judge answers first, then the critic answer) and `Geometry` with a stub detector:
  - `test_revision_page_shows_outcomes_and_new_critique`
  - `test_outcome_chip_text`: `"fixed"` and `"measured"` when geometry is confident on a proportion issue; `"judged"` otherwise
  - `test_closeness_line_shown`
  - `test_nothing_to_compare_when_parent_failed` (**Review Focus 5**)
  - `test_usage_limit_during_judging_sets_limit_and_retry_has_no_duplicates` (**Review Focus 4**): the first run raises `UsageLimitError` in the judge; Retry completes it; the page shows each outcome once
  - `test_first_version_page_unchanged`: no outcomes section
- [ ] **Step 2:** Run `.venv/bin/pytest tests/web -q`. Expected: FAIL.
- [ ] **Step 3:** Implement the worker, app, CLI and template changes above.
- [ ] **Step 4:** Run `.venv/bin/pytest -q`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: revision outcomes on the results page`.

### Task 8: Aligned overlay

**Files:**
- Modify: `artcrit/web/app.py`, `artcrit/web/templates/submission.html`
- Test: `tests/web/test_overlay.py`

**Interfaces:**
- Produces: `GET /submissions/{id}/overlay`, a PNG the size of the normalized drawing.
  - When `geometry.compare` is available, it's the cropped photo warped into drawing pixels with `cv2.warpAffine(photo, comparison.sim.matrix(), (drawing_w, drawing_h))`. `align(photo_pts, drawing_pts)` returns the photo→drawing transform, so no inversion is needed.
  - Otherwise it's the crop resized to the drawing's size (Plan 1 behaviour).
  - The header `X-Overlay: aligned | resized`.
  - `submission.html`'s overlay `<img>` uses this route, and the caption says "aligned to your drawing" or "not aligned (couldn't find outlines)".

- [ ] **Step 1:** Write the failing tests:
  - `test_overlay_same_size_as_drawing`
  - `test_overlay_aligned_header_when_outlines_found`
  - `test_overlay_resized_fallback_on_dark_drawing`
  - `test_aligned_overlay_matches_subject`: a synthetic photo with the subject shifted and scaled gives an overlay whose subject mask has IoU > 0.85 with the drawing's
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement the route and template changes.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: aligned overlay`.

### Task 9: "Help me measure" click-points

**Files:**
- Create: `artcrit/geometry/points.py`, `artcrit/web/templates/measure.html`, `artcrit/web/static/points.js`
- Modify: `artcrit/web/app.py`, `artcrit/web/templates/_outcomes.html`, `artcrit/outcomes.py`
- Test: `tests/geometry/test_points.py`, `tests/web/test_measure.py`

**Interfaces:**
- Produces:
  - `POINT_NAMES = ("left eye outer corner", "right eye outer corner", "nose tip", "chin", "hairline centre", "mouth centre")`
  - `points_error(drawing_pts, photo_pts) -> np.ndarray`: align photo points onto drawing points with a similarity fitted to all six (`cv2.estimateAffinePartial2D`), then return the per-point residual divided by the inter-eye distance
  - `measure_from_points(issue_box, old_pts, new_pts, photo_pts) -> GeometryMeasure`: source `"points"`, confident; uses the points inside `issue_box` (or all six)
  - Routes:
    - `GET /submissions/{id}/measure?issue={issue_id}`: three images (photo crop, previous version, this version) with `points.js`, which collects the six named points per image in order, in normalized coordinates
    - `POST /submissions/{id}/measure`: form `issue_id` and `points` JSON `{"photo": [[x, y]×6], "old": [...], "new": [...]}`; validates exactly 6 points each in [0, 1]; records event `help_measure` with the payload; appends a new outcome row with geometry source `points` through `final_verdict`; redirects to the submission
  - `_outcomes.html` shows a "Help me measure" link on `proportion` outcomes whose source is `judge`.

- [ ] **Step 1:** Write the failing tests:
  - `test_points_error_zero_for_similar_sets`
  - `test_points_error_flags_moved_chin`
  - `test_measure_link_only_on_judged_proportion`
  - `test_measure_post_appends_outcome_and_overrides`: the page then shows "measured"
  - `test_measure_rejects_wrong_point_count_422`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement the module, routes, template and JS.
- [ ] **Step 4:** Run `.venv/bin/pytest -q`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: help-me-measure click points`.

### Task 10: Live check and README

**Files:**
- Modify: `README.md` (roadmap: Plan 2 ✅; describe revisions and verdict sources), `tests/engine/test_claude_sdk_live.py` (add `test_live_judge_parses`)

- [ ] **Step 1:** Add `test_live_judge_parses`: an old long-jaw face, a new corrected face and the reference, judged with the real engine; assert the verdict is in the Verdict set.
- [ ] **Step 2:** Run `ARTCRIT_LIVE=1 .venv/bin/pytest -m live -q -s`. Expected: PASS, with a verdict of `fixed` or `partly` (printed).
- [ ] **Step 3:** Run `artcrit serve`. Upload v1 (the generated long-jaw, high-eyes phone photo from Plan 1's e2e run), then a revision with the jaw corrected but the eyes still high. Check that the outcome shows the jaw as fixed or partly, the eyes as not_fixed, the closeness line is positive, and the aligned overlay sits on the face.
- [ ] **Step 4:** Run `.venv/bin/pytest -q`. Expected: all pass.
- [ ] **Step 5:** Commit: `docs: README for revisions and judging`.
