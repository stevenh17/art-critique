import io
import json

import cv2
import numpy as np
from PIL import Image

from artcrit.geometry.outline import drawing_mask
from artcrit.geometry.service import Geometry

from .conftest import answer, png_bytes


def _png(img):
    buf = io.BytesIO()
    Image.fromarray(img[:, :, ::-1]).save(buf, format="PNG")
    return buf.getvalue()


def drawing_bytes(bg=245):
    img = np.full((640, 480, 3), bg, np.uint8)
    cv2.ellipse(img, (240, 320), (150, 210), 0, 0, 360, (20, 20, 20), 3)
    return _png(img)


def photo_bytes():
    img = np.full((500, 700, 3), 225, np.uint8)
    cv2.ellipse(img, (420, 230), (110, 155), 0, 0, 360, (80, 100, 150), -1)  # smaller and off-centre
    return _png(img)


def run(make_client, drawing=None, photo=None):
    client, _, app = make_client([answer()], geometry=Geometry(None, detector=lambda i, m: None))
    r = client.post("/uploads", files={"drawing": ("d.png", drawing or drawing_bytes(), "image/png"),
                                       "photo": ("p.png", photo or photo_bytes(), "image/png")},
                    data={"photo_source_url": "https://example.org/p", "photo_license": "CC0"}, follow_redirects=False)
    base = r.headers["location"].rsplit("/adjust", 1)[0]
    corners = json.dumps([[0, 0], [479, 0], [479, 639], [0, 639]])
    url = client.post(f"{base}/submit", data={"corners": corners, "photo_crop": "[0,0,1,1]"},
                      follow_redirects=False).headers["location"]
    view = app.state.store.get_submission(int(url.rsplit("/", 1)[1]))
    return client, url, view, app


def _decode(content):
    return cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)


def test_overlay_same_size_as_drawing(make_client):
    client, url, view, app = run(make_client)
    r = client.get(f"{url}/overlay")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert _decode(r.content).shape == app.state.images.load(view.normalized_path).shape


def test_overlay_aligned_header_when_outlines_found(make_client):
    client, url, _, _ = run(make_client)
    assert client.get(f"{url}/overlay").headers["X-Overlay"] == "aligned"


def test_overlay_resized_fallback_on_dark_drawing(make_client):
    client, url, _, _ = run(make_client, drawing=drawing_bytes(bg=100))
    assert client.get(f"{url}/overlay").headers["X-Overlay"] == "resized"


def test_aligned_overlay_matches_subject(make_client):
    client, url, view, app = run(make_client)
    overlay = _decode(client.get(f"{url}/overlay").content)
    subject = (np.abs(overlay.astype(int) - (80, 100, 150)).sum(axis=2) < 60)
    drawn = drawing_mask(app.state.images.load(view.normalized_path))
    iou = (subject & drawn).sum() / (subject | drawn).sum()
    assert iou > 0.85


def test_results_page_uses_overlay_route(make_client):
    client, url, _, _ = run(make_client)
    assert f'src="{url}/overlay"' in client.get(url).text


def test_overlay_falls_back_when_alignment_raises(make_client):
    class Broken:
        def compare(self, d, p):
            raise RuntimeError("boom")

        def faces(self, d, p):
            raise RuntimeError("boom")

    client, _, app = make_client([], geometry=Broken())
    from .conftest import submit, upload

    url = submit(client, upload(client).headers["location"]).headers["location"]
    sid = int(url.rsplit("/", 1)[1])
    app.state.store.add_status(sid, "done")
    r = client.get(f"{url}/overlay")
    assert r.status_code == 200 and r.headers["X-Overlay"] == "resized"
