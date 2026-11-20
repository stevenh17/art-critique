"""FastAPI app: upload → adjust → critique → results."""

import json
import secrets
import threading
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from artcrit.config import Settings
from artcrit.engine.base import AgentEngine
from artcrit.imaging.deskew import find_paper, full_corners, normalize, warp
from artcrit.imaging.load import UnsupportedImageError, load_image
from artcrit.store.images import ImageStore
from artcrit.store.sessions import SessionStore
from artcrit.web.worker import run_critique

HERE = Path(__file__).parent


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
               run_in_background: Callable[[Callable[[], None]], None] = _thread) -> FastAPI:
    app = FastAPI(title="Art critique")
    store = SessionStore(settings.db_path)
    images = ImageStore(settings.images_dir)
    templates = Jinja2Templates(directory=HERE / "templates")
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    app.state.store, app.state.images, app.state.templates = store, images, templates

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
        run_in_background(lambda: run_critique(submission_id, store, images, engine, settings))

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
        try:
            d_img, p_img = load_image(await drawing.read()), load_image(await photo.read())
        except UnsupportedImageError as e:
            raise HTTPException(422, f"Could not read image: {e}")
        corners = find_paper(d_img) or full_corners(d_img)
        token = secrets.token_hex(8)
        meta = {
            "drawing": images.save(d_img, "original"), "photo": images.save(p_img, "photo"),
            "corners": [list(c) for c in corners], "photo_source_url": photo_source_url.strip(),
            "photo_license": photo_license.strip(), "publish": publish is not None,
        }
        path = upload_path(token)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(meta))
        return RedirectResponse(f"/uploads/{token}/adjust", status_code=303)

    @app.get("/uploads/{token}/adjust", response_class=HTMLResponse)
    def adjust(request: Request, token: str):
        meta = load_upload(token)
        return templates.TemplateResponse(request, "adjust.html",
                                          {"token": token, "meta": meta, "corners_json": json.dumps(meta["corners"])})

    @app.post("/uploads/{token}/submit")
    def submit(token: str, corners: str = Form(...), photo_crop: str = Form(...)):
        meta = load_upload(token)
        pts, box = _parse_corners(corners), _parse_box(photo_crop)
        normalized = normalize(warp(images.load(meta["drawing"]), pts))
        drawing_id = store.add_drawing(meta["photo"], box, meta["photo_source_url"], meta["photo_license"], meta["publish"])
        sid = store.add_submission(drawing_id, 1, None, meta["drawing"], images.save(normalized, "drawing"), pts)
        start(sid)
        return RedirectResponse(f"/submissions/{sid}", status_code=303)

    def get_view(submission_id: int):
        view = store.get_submission(submission_id)
        if view is None:
            raise HTTPException(404, "submission not found")
        return view

    @app.get("/submissions/{submission_id}", response_class=HTMLResponse)
    def submission(request: Request, submission_id: int):
        return templates.TemplateResponse(request, "submission.html", {"s": get_view(submission_id)})

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

    return app
