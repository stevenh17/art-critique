import io
import json

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from artcrit.config import Settings
from artcrit.engine.base import AgentResult
from artcrit.engine.fake import FakeEngine
from artcrit.web.app import create_app

GOOD = json.dumps({"issues": [
    {"category": "proportion", "title": "Jaw too long", "instruction": "Shorten the chin by about a quarter head.",
     "drawing_cells": ["C7", "D7"], "photo_cells": ["C6", "D6"]},
    {"category": "values", "title": "Shadow too light", "instruction": "Darken the cheek shadow a step.",
     "drawing_cells": ["B4"], "photo_cells": ["B4"]},
]})


def answer(text=GOOD):
    return lambda tools: AgentResult(text, [], "fake-model")


def png_bytes(w=400, h=300, paper=True) -> bytes:
    img = np.full((h, w, 3), 30, np.uint8)
    if paper:
        cv2.rectangle(img, (60, 40), (w - 60, h - 40), (245, 245, 245), -1)
        cv2.circle(img, (w // 2, h // 2), 50, (20, 20, 20), 3)
    buf = io.BytesIO()
    Image.fromarray(img[:, :, ::-1]).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def make_client(tmp_path):
    def _make(script):
        lessons = tmp_path / "lessons"
        (lessons / "topics").mkdir(parents=True, exist_ok=True)
        (lessons / "core.md").write_text("# Core\nMeasure.\n")
        settings = Settings(data_dir=tmp_path / "data", lessons_dir=lessons, repo_dir=tmp_path)
        engine = FakeEngine(script)
        app = create_app(settings, engine, run_in_background=lambda fn: fn())
        return TestClient(app), engine, app

    return _make


def upload(client, license="Unsplash", drawing=None):
    return client.post(
        "/uploads",
        files={"drawing": ("d.png", drawing or png_bytes(), "image/png"), "photo": ("p.png", png_bytes(paper=False), "image/png")},
        data={"photo_source_url": "https://unsplash.com/photos/x", "photo_license": license, "publish": "on"},
        follow_redirects=False,
    )


def submit(client, adjust_url):
    token_url = adjust_url.rsplit("/adjust", 1)[0]
    corners = json.dumps([[60, 40], [340, 40], [340, 260], [60, 260]])
    return client.post(f"{token_url}/submit", data={"corners": corners, "photo_crop": json.dumps([0, 0, 1, 1])},
                       follow_redirects=False)
