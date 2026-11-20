import json

import numpy as np

from artcrit.critic import BUDGET_USED, MAX_TOOL_CALLS, critique
from artcrit.engine.base import AgentResult
from artcrit.engine.fake import FakeEngine
from artcrit.geometry.service import Geometry

from .geometry.test_outline import ellipse_drawing
from .geometry.test_service import photo_like

GOOD = json.dumps({"issues": [
    {"category": "proportion", "title": "A", "instruction": "x", "drawing_cells": ["A1"], "photo_cells": ["A1"]},
    {"category": "values", "title": "B", "instruction": "y", "drawing_cells": ["B2"], "photo_cells": ["B2"]}]})


def _lessons(tmp_path):
    (tmp_path / "topics").mkdir()
    (tmp_path / "core.md").write_text("# Core\nMeasure.\n")
    return tmp_path


def _run_with(tmp_path, fn, geometry):
    seen = {}

    def step(tools):
        seen["out"] = fn({t.name: t for t in tools})
        return AgentResult(GOOD, [], "m")

    critique(ellipse_drawing(), photo_like(), _lessons(tmp_path), FakeEngine([step]), geometry=geometry)
    return seen["out"]


def test_outline_compare_tool_text_and_image(tmp_path):
    out = _run_with(tmp_path, lambda t: t["outline_compare"].handler({"cells": ["C7", "D7"]}), Geometry(None))
    text = next(b["text"] for b in out if b["type"] == "text")
    assert "overall" in text.lower() and "region" in text.lower() and "scale" in text.lower()
    assert any(b["type"] == "image" for b in out)


def test_outline_compare_without_geometry_is_unavailable(tmp_path):
    out = _run_with(tmp_path, lambda t: t["outline_compare"].handler({}), None)
    assert out[0]["type"] == "text" and "unavailable" in out[0]["text"]


def test_face_tool_unavailable_message(tmp_path):
    g = Geometry(None, detector=lambda img, model: None)
    out = _run_with(tmp_path, lambda t: t["face_landmarks"].handler({}), g)
    assert "unavailable" in out[0]["text"]


def test_geometry_tools_share_budget(tmp_path):
    def burn(t):
        names = ["zoom", "outline_compare", "face_landmarks", "grid_overlay"]
        args = {"zoom": {"image": "drawing", "cells": ["A1"]}, "grid_overlay": {"image": "photo"}}
        outs = [t[names[i % 4]].handler(args.get(names[i % 4], {})) for i in range(MAX_TOOL_CALLS)]
        return outs + [t["outline_compare"].handler({})]

    outs = _run_with(tmp_path, burn, Geometry(None, detector=lambda i, m: None))
    assert all(BUDGET_USED not in str(o) for o in outs[:MAX_TOOL_CALLS])
    assert outs[-1][0]["text"] == BUDGET_USED
