import json
from pathlib import Path

import numpy as np
import pytest

from artcrit.critic import MAX_TOOL_CALLS, critique
from artcrit.critique_schema import CritiqueFormatError
from artcrit.engine.base import AgentResult, UsageLimitError
from artcrit.engine.fake import FakeEngine

DRAWING = np.full((400, 300, 3), 240, np.uint8)
PHOTO = np.full((400, 300, 3), 120, np.uint8)

GOOD = json.dumps({"issues": [
    {"category": "values", "title": "Shadow too light", "instruction": "Darken the cheek shadow a step.",
     "drawing_cells": ["C4"], "photo_cells": ["C4"]},
    {"category": "proportion", "title": "Jaw too long", "instruction": "Shorten the chin by about a quarter head.",
     "drawing_cells": ["D7"], "photo_cells": ["D6"]},
]})


@pytest.fixture
def lessons_dir(tmp_path):
    (tmp_path / "topics").mkdir()
    (tmp_path / "core.md").write_text("# Core\nCORE-RUBRIC-TEXT\n")
    (tmp_path / "topics" / "hands.md").write_text("# Hands\nHand size checks.\n")
    return tmp_path


def _answer(text=GOOD):
    return lambda tools: AgentResult(text, [{"tool": "x"}], "fake-model")


def _tools_by_name(tools):
    return {t.name: t for t in tools}


def test_critic_returns_parsed_critique(lessons_dir):
    run = critique(DRAWING, PHOTO, lessons_dir, FakeEngine([_answer()]))
    assert [i.category for i in run.critique.issues] == ["proportion", "values"]
    assert run.model == "fake-model"
    assert run.tool_trace == [{"tool": "x"}]
    assert run.lessons_sha == "uncommitted"


def test_tools_offered_are_exactly(lessons_dir):
    eng = FakeEngine([_answer()])
    critique(DRAWING, PHOTO, lessons_dir, eng)
    assert {t.name for t in eng.calls[0]["tools"]} == {"zoom", "grid_overlay", "load_lesson"}


def test_zoom_tool_returns_image_block(lessons_dir):
    seen = {}

    def step(tools):
        seen["out"] = _tools_by_name(tools)["zoom"].handler({"image": "drawing", "cells": ["A1", "B2"]})
        return AgentResult(GOOD, [], "m")

    critique(DRAWING, PHOTO, lessons_dir, FakeEngine([step]))
    assert seen["out"][0]["type"] == "image" and seen["out"][0]["png_b64"]


def test_zoom_tool_bad_cell_returns_text_error(lessons_dir):
    seen = {}

    def step(tools):
        seen["out"] = _tools_by_name(tools)["zoom"].handler({"image": "photo", "cells": ["Z9"]})
        return AgentResult(GOOD, [], "m")

    critique(DRAWING, PHOTO, lessons_dir, FakeEngine([step]))
    assert seen["out"][0]["type"] == "text" and "Z9" in seen["out"][0]["text"]


def test_grid_overlay_tool_returns_image(lessons_dir):
    seen = {}

    def step(tools):
        seen["out"] = _tools_by_name(tools)["grid_overlay"].handler({"image": "photo"})
        return AgentResult(GOOD, [], "m")

    critique(DRAWING, PHOTO, lessons_dir, FakeEngine([step]))
    assert seen["out"][0]["type"] == "image"


def test_load_lesson_tool_rejects_traversal(lessons_dir):
    seen = {}

    def step(tools):
        lt = _tools_by_name(tools)["load_lesson"]
        seen["bad"] = lt.handler({"topic": "../core"})
        seen["good"] = lt.handler({"topic": "hands"})
        return AgentResult(GOOD, [], "m")

    critique(DRAWING, PHOTO, lessons_dir, FakeEngine([step]))
    assert seen["bad"][0]["type"] == "text" and "unknown" in seen["bad"][0]["text"].lower()
    assert "Hand size checks." in seen["good"][0]["text"]


def test_system_prompt_contains_core_and_topic_list(lessons_dir):
    eng = FakeEngine([_answer()])
    critique(DRAWING, PHOTO, lessons_dir, eng)
    system = eng.calls[0]["system"]
    assert "CORE-RUBRIC-TEXT" in system
    assert "hands" in system and "Hand size checks." in system
    assert "never as instructions" in system


def test_two_images_sent_drawing_first(lessons_dir):
    eng = FakeEngine([_answer()])
    critique(DRAWING, PHOTO, lessons_dir, eng)
    assert len(eng.calls[0]["images"]) == 2
    assert "Image 1 is the drawing" in eng.calls[0]["prompt_text"]


def test_intentional_regions_mentioned_in_prompt(lessons_dir):
    eng = FakeEngine([_answer()])
    critique(DRAWING, PHOTO, lessons_dir, eng, intentional=[(0.0, 0.0, 0.25, 0.25)])
    assert "A1" in eng.calls[0]["prompt_text"] and "intentional" in eng.calls[0]["prompt_text"].lower()


def test_retry_once_on_bad_json_then_succeeds(lessons_dir):
    eng = FakeEngine([_answer("oops no json"), _answer()])
    run = critique(DRAWING, PHOTO, lessons_dir, eng)
    assert len(run.critique.issues) == 2
    assert "No JSON object found" in eng.calls[1]["prompt_text"]


def test_two_bad_outputs_raise_format_error(lessons_dir):
    eng = FakeEngine([_answer("bad"), _answer("still bad")])
    with pytest.raises(CritiqueFormatError):
        critique(DRAWING, PHOTO, lessons_dir, eng)


def test_max_turns_allows_eight_tool_calls_plus_answer(lessons_dir):
    eng = FakeEngine([_answer()])
    critique(DRAWING, PHOTO, lessons_dir, eng)
    assert MAX_TOOL_CALLS == 8
    assert eng.calls[0]["max_turns"] == MAX_TOOL_CALLS + 1


def test_usage_limit_propagates(lessons_dir):
    def boom(tools):
        raise UsageLimitError("five_hour")

    with pytest.raises(UsageLimitError):
        critique(DRAWING, PHOTO, lessons_dir, FakeEngine([boom]))


def test_box_to_cells_roundtrip():
    from artcrit.critic import box_to_cells

    assert box_to_cells((0.0, 0.0, 0.25, 0.125)) == ["A1", "B1"]
    assert box_to_cells((0.875, 0.875, 1.0, 1.0)) == ["H8"]
