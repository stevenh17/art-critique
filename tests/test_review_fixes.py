"""Regression tests for the final whole-branch review findings (C-1, I-1..I-6)."""

import asyncio
import base64
import io
import json

import cv2
import numpy as np
import pytest
from PIL import Image
from claude_agent_sdk import ResultMessage
from claude_agent_sdk._errors import ResultError

from artcrit.critic import MAX_TOOL_CALLS, critique
from artcrit.engine import claude_sdk
from artcrit.engine.base import AgentResult, EngineError, UsageLimitError
from artcrit.engine.fake import FakeEngine
from artcrit.imaging.deskew import validate_corners
from artcrit.imaging.load import load_image
from artcrit.store.sessions import SessionStore

GOOD = json.dumps({"issues": [
    {"category": "proportion", "title": "A", "instruction": "x", "drawing_cells": ["A1"], "photo_cells": ["A1"]},
    {"category": "values", "title": "B", "instruction": "y", "drawing_cells": ["B2"], "photo_cells": ["B2"]}]})
MAX_B64 = 3_500_000


@pytest.fixture
def lessons_dir(tmp_path):
    (tmp_path / "topics").mkdir()
    (tmp_path / "core.md").write_text("# Core\nMeasure.\n")
    return tmp_path


# ---- C-1: images sent to the model are bounded ----
def test_large_photo_is_downscaled_before_sending(lessons_dir):
    photo = np.random.default_rng(1).integers(0, 255, (3000, 4000, 3), dtype=np.uint8)
    drawing = np.full((1600, 1200, 3), 240, np.uint8)
    seen = {}

    def step(tools):
        seen["grid"] = {t.name: t for t in tools}["grid_overlay"].handler({"image": "photo"})[0]["png_b64"]
        return AgentResult(GOOD, [], "m")

    eng = FakeEngine([step])
    critique(drawing, photo, lessons_dir, eng)
    for b64 in [*eng.calls[0]["images"], seen["grid"]]:
        assert len(b64) <= MAX_B64
        img = cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8), cv2.IMREAD_COLOR)
        assert max(img.shape[:2]) <= 1568


# ---- I-1: SDK errors are not parse failures ----
def _fake_query(messages, exc):
    async def gen(prompt, options):
        for m in messages:
            yield m
        if exc:
            raise exc
    return gen


def _result(**kw):
    base = dict(subtype="success", duration_ms=1, duration_api_ms=1, is_error=True, num_turns=1, session_id="s")
    base.update(kw)
    return ResultMessage(**base)


def _run(monkeypatch, messages, exc):
    monkeypatch.setattr(claude_sdk, "query", _fake_query(messages, exc))
    return claude_sdk.ClaudeSDKEngine().run("sys", "p", [], [], 3)


def test_api_error_raises_engine_error_not_text(monkeypatch):
    err = ResultError("x", {"subtype": "success", "result": "API Error: request too large", "api_error_status": 413,
                            "terminal_reason": "api_error"})
    with pytest.raises(EngineError, match="request too large"):
        _run(monkeypatch, [_result(result="API Error: request too large")], err)


def test_429_result_error_is_usage_limit(monkeypatch):
    err = ResultError("x", {"subtype": "success", "result": "API Error: 429", "api_error_status": 429})
    with pytest.raises(UsageLimitError):
        _run(monkeypatch, [], err)


def test_max_turns_result_error_is_swallowed(monkeypatch):
    err = ResultError("x", {"subtype": "error_max_turns", "terminal_reason": "max_turns"})
    assert _run(monkeypatch, [], err).text == ""


def test_engine_error_is_not_retried_by_critic(lessons_dir):
    calls = []

    def boom(tools):
        calls.append(1)
        raise EngineError("API Error: overloaded")

    with pytest.raises(EngineError):
        critique(np.zeros((50, 50, 3), np.uint8), np.zeros((50, 50, 3), np.uint8), lessons_dir, FakeEngine([boom, boom]))
    assert len(calls) == 1


# ---- I-2: tool budget enforced inside the tools ----
def test_tool_budget_enforced(lessons_dir):
    outs = []

    def step(tools):
        z = {t.name: t for t in tools}["zoom"]
        outs.extend(z.handler({"image": "drawing", "cells": ["A1"]}) for _ in range(MAX_TOOL_CALLS + 2))
        return AgentResult(GOOD, [], "m")

    eng = FakeEngine([step])
    critique(np.zeros((80, 80, 3), np.uint8), np.zeros((80, 80, 3), np.uint8), lessons_dir, eng)
    assert all(o[0]["type"] == "image" for o in outs[:MAX_TOOL_CALLS])
    assert all(o[0]["type"] == "text" and "final JSON" in o[0]["text"] for o in outs[MAX_TOOL_CALLS:])
    assert eng.calls[0]["max_turns"] > MAX_TOOL_CALLS + 1  # turn cap is only a backstop


# ---- I-3: corners validated ----
SHAPE = (600, 800, 3)


def test_validate_corners_reorders_crossed_handles():
    crossed = ((700, 100), (100, 100), (700, 500), (100, 500))  # TL and TR swapped
    assert validate_corners(crossed, SHAPE) == ((100.0, 100.0), (700.0, 100.0), (700.0, 500.0), (100.0, 500.0))


def test_validate_corners_clamps_to_image():
    out = validate_corners(((-50, -50), (900, 0), (900, 700), (0, 700)), SHAPE)
    assert out == ((0.0, 0.0), (799.0, 0.0), (799.0, 599.0), (0.0, 599.0))


@pytest.mark.parametrize("pts", [((5, 5),) * 4, ((0, 0), (10, 0), (10, 10), (0, 10))])
def test_validate_corners_rejects_degenerate(pts):
    with pytest.raises(ValueError):
        validate_corners(pts, SHAPE)


# ---- I-4: transparent drawings composite onto white ----
def test_transparent_png_loads_on_white():
    img = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    img.putpixel((20, 20), (0, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    arr = load_image(buf.getvalue())
    assert tuple(arr[0, 0]) == (255, 255, 255) and tuple(arr[20, 20]) == (0, 0, 0)


# ---- I-5: interrupted submissions become retryable on startup ----
def test_interrupted_submissions_marked_failed_on_startup(tmp_path):
    from artcrit.config import Settings
    from artcrit.web.app import create_app

    settings = Settings(data_dir=tmp_path / "data", lessons_dir=tmp_path, repo_dir=tmp_path)
    store = SessionStore(settings.db_path)
    d = store.add_drawing("p.png", (0, 0, 1, 1), "https://x", "CC0", True)
    s = store.add_submission(d, 1, None, "o.png", "n.png", ((0, 0), (1, 0), (1, 1), (0, 1)))
    store.add_status(s, "running")
    create_app(settings, FakeEngine([]))
    v = store.get_submission(s)
    assert v.status == "failed" and "interrupted" in v.status_detail
