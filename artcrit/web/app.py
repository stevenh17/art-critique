"""FastAPI app: upload → adjust → critique → results."""

import json
import logging
import secrets
from dataclasses import asdict

import cv2
import numpy as np
from urllib.parse import urlparse
import threading
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from artcrit.config import Settings
from artcrit.engine.base import AgentEngine
from artcrit.imaging.deskew import find_paper, full_corners, normalize, validate_corners, warp
from artcrit.imaging.load import UnsupportedImageError, load_image
from artcrit.imaging.regions import crop, zoom
from artcrit.store.images import ImageStore
from artcrit.store.sessions import SessionStore
from artcrit.geometry.points import POINT_NAMES, measure_from_points
from artcrit.geometry.service import Geometry
from artcrit.judge import JudgeResult
from artcrit.outcomes import OutcomeRow, final_verdict
from artcrit.web.worker import run_submission

HERE = Path(__file__).parent
log = logging.getLogger(__name__)
ISSUE_EVENTS = ("thumb_up", "thumb_down", "unclear", "intentional", "show_me")


def _thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


def _parse_box(raw: str) -> tuple[float, float, float, float]:
    try:
        x0, y0, x1, y1 = (min(max(float(v), 0.0), 1.0) for v in json.loads(raw))
    except (ValueError, TypeError):
        raise HTTPException(422, "photo_crop must be [x0, y0, x1, y1]")
    if x1 - x0 < 0.02 or y1 - y0 < 0.02:
        raise HTTPException(422, "photo crop is too small")
    return (x0, y0, x1, y1)


def _parse_corners(raw: str):
    try:
        pts = [(float(x), float(y)) for x, y in json.loads(raw)]
    except (ValueError, TypeError):
        raise HTTPException(422, "corners must be four [x, y] points")
    if len(pts) != 4:
        raise HTTPException(422, "corners must be four [x, y] points")
    return tuple(pts)


def create_app(settings: Settings, engine: AgentEngine,
               run_in_background: Callable[[Callable[[], None]], None] = _thread,
               geometry: Geometry | None = None) -> FastAPI:
    app = FastAPI(title="Art critique")
    store = SessionStore(settings.db_path)
    images = ImageStore(settings.images_dir)
    templates = Jinja2Templates(directory=HERE / "templates")
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    app.state.store, app.state.images, app.state.templates = store, images, templates
    for sid in store.unfinished_submissions():  # a previous server stopped mid-critique
        store.add_status(sid, "failed", "interrupted — retry")

    def upload_path(token: str) -> Path:
        if not token.isalnum():
            raise HTTPException(404)
        return Path(settings.uploads_dir) / f"{token}.json"

    def load_upload(token: str) -> dict:
        p = upload_path(token)
        if not p.is_file():
            raise HTTPException(404, "upload not found")
        return json.loads(p.read_text())

    def start(submission_id: int) -> None:
        run_in_background(lambda: run_submission(submission_id, store, images, engine, settings, geometry))

    @app.get("/images/{rel_path:path}")
    def image(rel_path: str):
        try:
            return FileResponse(images.resolve(rel_path), media_type="image/png")
        except FileNotFoundError:
            raise HTTPException(404)

    @app.get("/", response_class=HTMLResponse)
    def upload_form(request: Request):
        return templates.TemplateResponse(request, "upload.html", {})

    @app.post("/uploads")
    async def create_upload(drawing: UploadFile = File(...), photo: UploadFile = File(...),
                            photo_source_url: str = Form(...), photo_license: str = Form(...),
                            publish: str | None = Form(None)):
        if not photo_license.strip() or not photo_source_url.strip():
            raise HTTPException(422, "reference photo source and license are required")
        if urlparse(photo_source_url.strip()).scheme not in ("http", "https"):
            raise HTTPException(422, "reference photo source must be an http(s) link")
        try:
            d_img, p_img = load_image(await drawing.read()), load_image(await photo.read())
        except UnsupportedImageError as e:
            raise HTTPException(422, f"Could not read image: {e}")
        corners = find_paper(d_img) or full_corners(d_img)
        token = save_token({
            "drawing": images.save(d_img, "original"), "photo": images.save(p_img, "photo"),
            "corners": [list(c) for c in corners], "photo_source_url": photo_source_url.strip(),
            "photo_license": photo_license.strip(), "publish": publish is not None,
        })
        return RedirectResponse(f"/uploads/{token}/adjust", status_code=303)

    def save_token(meta: dict) -> str:
        token = secrets.token_hex(8)
        path = upload_path(token)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(meta))
        return token

    def latest_or_404(drawing_id: int) -> int:
        sid = store.latest_submission(drawing_id)
        if sid is None:
            raise HTTPException(404, "drawing not found")
        return sid

    @app.get("/drawings/{drawing_id}/revise", response_class=HTMLResponse)
    def revise_form(request: Request, drawing_id: int):
        latest_or_404(drawing_id)
        return templates.TemplateResponse(request, "revise.html", {"drawing_id": drawing_id})

    @app.post("/drawings/{drawing_id}/revisions")
    async def create_revision(drawing_id: int, drawing: UploadFile = File(...)):
        latest_or_404(drawing_id)
        try:
            d_img = load_image(await drawing.read())
        except UnsupportedImageError as e:
            raise HTTPException(422, f"Could not read image: {e}")
        corners = find_paper(d_img) or full_corners(d_img)
        token = save_token({"drawing": images.save(d_img, "original"), "corners": [list(c) for c in corners],
                            "drawing_id": drawing_id})
        return RedirectResponse(f"/uploads/{token}/adjust", status_code=303)

    @app.get("/uploads/{token}/adjust", response_class=HTMLResponse)
    def adjust(request: Request, token: str):
        meta = load_upload(token)
        return templates.TemplateResponse(request, "adjust.html",
                                          {"token": token, "meta": meta, "corners_json": json.dumps(meta["corners"])})

    @app.post("/uploads/{token}/submit")
    def submit(token: str, corners: str = Form(...), photo_crop: str | None = Form(None)):
        meta = load_upload(token)
        pts = _parse_corners(corners)
        revision_of = meta.get("drawing_id")
        if revision_of is None and photo_crop is None:
            raise HTTPException(422, "photo_crop is required")
        original = images.load(meta["drawing"])
        try:
            pts = validate_corners(pts, original.shape)
        except ValueError as e:
            raise HTTPException(422, f"Corners: {e}")
        normalized = images.save(normalize(warp(original, pts)), "drawing")
        if revision_of is None:
            drawing_id = store.add_drawing(meta["photo"], _parse_box(photo_crop), meta["photo_source_url"],
                                           meta["photo_license"], meta["publish"])
            version, parent = 1, None
        else:
            drawing_id, parent = revision_of, latest_or_404(revision_of)
            version = max(v for _, v in store.versions(drawing_id)) + 1
        sid = store.add_submission(drawing_id, version, parent, meta["drawing"], normalized, pts)
        start(sid)
        return RedirectResponse(f"/submissions/{sid}", status_code=303)

    def get_view(submission_id: int):
        view = store.get_submission(submission_id)
        if view is None:
            raise HTTPException(404, "submission not found")
        return view

    @app.get("/submissions/{submission_id}", response_class=HTMLResponse)
    def submission(request: Request, submission_id: int):
        view = get_view(submission_id)
        ctx = {"s": view, "versions": store.versions(view.drawing_id), "prev": None, "outcomes": [], "closeness": None,
               "overlay_kind": overlay_for(view)[1] if view.issues else None}
        if view.parent_id is not None:
            ctx["prev"] = store.get_submission(view.parent_id)
            ctx["outcomes"] = store.outcomes_for(view.id)
            metrics = store.revision_metrics(view.id)
            if metrics and metrics[0] and metrics[1] is not None:
                ctx["closeness"] = 1 - metrics[1] / metrics[0]
        return templates.TemplateResponse(request, "submission.html", ctx)

    @app.get("/submissions/{submission_id}/status", response_class=HTMLResponse)
    def status(request: Request, submission_id: int):
        view = get_view(submission_id)
        resp = templates.TemplateResponse(request, "_status.html", {"s": view})
        if view.status not in ("queued", "running"):
            resp.headers["HX-Refresh"] = "true"
        return resp

    @app.post("/submissions/{submission_id}/retry")
    def retry(submission_id: int):
        view = get_view(submission_id)
        if view.status not in ("failed", "limit"):
            raise HTTPException(409, f"cannot retry a submission that is {view.status}")
        store.add_status(submission_id, "queued", "retry")
        start(submission_id)
        return RedirectResponse(f"/submissions/{submission_id}", status_code=303)

    overlay_cache: dict[int, tuple[bytes, str]] = {}

    def overlay_for(view) -> tuple[bytes, str]:
        """The cropped photo in drawing pixels: aligned when outlines are found, else just resized."""
        if view.id not in overlay_cache:
            drawing = images.load(view.normalized_path)
            photo = crop(images.load(view.photo_path), view.photo_crop)
            h, w = drawing.shape[:2]
            out, kind = cv2.resize(photo, (w, h), interpolation=cv2.INTER_AREA), "resized"
            try:
                comp = geometry.compare(drawing, photo) if geometry is not None else None
                if comp is not None and comp.available:
                    out, kind = cv2.warpAffine(photo, comp.full_matrix(), (w, h), flags=cv2.INTER_LINEAR,
                                               borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255)), "aligned"
            except Exception:  # measurement problems must never break the results page
                log.exception("overlay alignment failed for submission %s", view.id)
            overlay_cache[view.id] = (cv2.imencode(".png", out)[1].tobytes(), kind)
        return overlay_cache[view.id]

    @app.get("/submissions/{submission_id}/overlay")
    def overlay(submission_id: int):
        data, kind = overlay_for(get_view(submission_id))
        return Response(data, media_type="image/png", headers={"X-Overlay": kind})

    def photo_crop_path(view) -> str:
        return images.save(crop(images.load(view.photo_path), view.photo_crop), "photo-crop")

    @app.get("/submissions/{submission_id}/photo-crop")
    def photo_crop(submission_id: int):
        return FileResponse(images.resolve(photo_crop_path(get_view(submission_id))), media_type="image/png")

    def measure_context(submission_id: int, issue_id: int):
        view = get_view(submission_id)
        if view.parent_id is None:
            raise HTTPException(404, "measuring needs a revision")
        outcome = next((o for o in store.outcomes_for(view.id) if o.issue_id == issue_id), None)
        if outcome is None:
            raise HTTPException(404, "no outcome for that issue")
        return view, store.get_submission(view.parent_id), outcome

    @app.get("/submissions/{submission_id}/measure", response_class=HTMLResponse)
    def measure_form(request: Request, submission_id: int, issue: int):
        view, prev, outcome = measure_context(submission_id, issue)
        return templates.TemplateResponse(request, "measure.html", {
            "s": view, "prev": prev, "outcome": outcome, "names": POINT_NAMES,
            "photo_src": f"/submissions/{view.id}/photo-crop"})

    @app.post("/submissions/{submission_id}/measure")
    def measure_submit(submission_id: int, issue_id: int = Form(...), points: str = Form(...)):
        view, prev, outcome = measure_context(submission_id, issue_id)
        try:
            raw = json.loads(points)
            pts = {k: np.array(raw[k], float) for k in ("photo", "old", "new")}
        except (ValueError, KeyError, TypeError):
            raise HTTPException(422, "points must be {photo, old, new} lists of [x, y]")
        if any(p.shape != (len(POINT_NAMES), 2) or (p < 0).any() or (p > 1).any() for p in pts.values()):
            raise HTTPException(422, f"each image needs exactly {len(POINT_NAMES)} points inside the image")
        old_img, new_img = images.load(prev.normalized_path), images.load(view.normalized_path)
        photo = crop(images.load(view.photo_path), view.photo_crop)
        px = lambda p, img: p * (img.shape[1], img.shape[0])  # noqa: E731
        issue = next(i for i in prev.issues if i.id == issue_id)
        measure = measure_from_points(issue.drawing_box, px(pts["old"], old_img), px(pts["new"], new_img),
                                      px(pts["photo"], photo), old_img.shape)
        verdict, source, disagree = final_verdict(
            outcome.category, JudgeResult(outcome.judge_verdict, outcome.judge_reason, ""), measure)
        store.add_event("help_measure", issue_id=issue_id, submission_id=view.id, payload=raw)
        store.add_outcome(OutcomeRow(issue_id, view.id, outcome.judge_verdict, outcome.judge_reason,
                                     json.dumps(asdict(measure)), verdict, source, disagree))
        return RedirectResponse(f"/submissions/{view.id}", status_code=303)

    @app.post("/issues/{issue_id}/events", response_class=HTMLResponse)
    def issue_event(request: Request, issue_id: int, type: str = Form(...)):
        if type not in ISSUE_EVENTS:
            raise HTTPException(422, f"unknown event type {type!r}")
        row = store.get_issue(issue_id)
        if row is None:
            raise HTTPException(404, "issue not found")
        store.add_event(type, issue_id=issue_id, submission_id=row["submission_id"])
        view = get_view(row["submission_id"])
        issue = next(i for i in view.issues if i.id == issue_id)
        zooms = None
        if type == "show_me":
            photo = crop(images.load(view.photo_path), view.photo_crop)
            zooms = (images.save(zoom(images.load(view.normalized_path), issue.drawing_box, pad=0.03), "zoom"),
                     images.save(zoom(photo, issue.photo_box, pad=0.03), "zoom"))
        return templates.TemplateResponse(request, "_issue.html", {"issue": issue, "zooms": zooms})

    return app
