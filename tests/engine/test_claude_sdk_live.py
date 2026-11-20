"""Live check against the real engine. Run with: ARTCRIT_LIVE=1 pytest -m live"""

import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from artcrit.critic import critique
from artcrit.engine.claude_sdk import ClaudeSDKEngine

pytestmark = [pytest.mark.live, pytest.mark.skipif(os.environ.get("ARTCRIT_LIVE") != "1", reason="set ARTCRIT_LIVE=1")]
REPO = Path(__file__).resolve().parents[2]


def _face(jaw_extra: int) -> np.ndarray:
    img = np.full((480, 360, 3), 245, np.uint8)
    cv2.ellipse(img, (180, 220 + jaw_extra // 2), (110, 150 + jaw_extra // 2), 0, 0, 360, (40, 40, 40), 3)
    for x in (135, 225):
        cv2.ellipse(img, (x, 200 - jaw_extra), (22, 10), 0, 0, 360, (40, 40, 40), 3)
    cv2.line(img, (180, 230), (180, 275), (40, 40, 40), 3)
    cv2.line(img, (150, 315), (210, 315), (40, 40, 40), 3)
    return img


def test_live_critique_parses():
    run = critique(_face(60), _face(0), REPO / "lessons", ClaudeSDKEngine(), repo_dir=REPO)
    print(run.model, [(i.category, i.title) for i in run.critique.issues], len(run.tool_trace))
    assert 2 <= len(run.critique.issues) <= 3


def test_live_judge_parses():
    from artcrit.judge import VERDICTS, judge_issue

    res = judge_issue("proportion", "Head too long: chin far too low",
                      "Shorten the lower face so the chin sits about a quarter head-height higher.",
                      _face(60), _face(5), _face(0), ClaudeSDKEngine())
    print(res)
    assert res.verdict in VERDICTS


def test_live_dreamer_proposes_valid_edit_or_none():
    from artcrit.dreamer.agent import dream
    from artcrit.dreamer.export import EvidenceRecord, Export, Watermark
    from artcrit.dreamer.workspace import LessonWorkspace

    def rec(n, fixed):
        return EvidenceRecord(f"s{n}", 1, "proportion", "Eyes placed too high on the head",
                              "Move both eyes down to about halfway between the top of the head and the chin.",
                              ["Check eye line before features"], {"thumb_up": 1, "thumb_down": 0, "unclear": 0, "show_me": 0},
                              False, [{"verdict": "fixed" if fixed else "not_fixed", "measured": fixed, "disagreement": False}])

    export = Export([rec(101, True), rec(102, True), rec(103, False), rec(104, True), rec(105, True)],
                    Watermark(105, 5, 20), [])
    base = LessonWorkspace.from_ref(REPO, "main")
    res = dream(export, base, ClaudeSDKEngine(), [], today="2026-11-21")
    print("\nOK:", res.ok, "| model:", res.model, "\nSUMMARY:", res.summary, "\nCHANGES:", res.changes,
          "\nFAILURES:", res.failures, "\nCHANGED FILES:", list(res.workspace.changed(base)))
    for path, text in res.workspace.changed(base).items():
        print(f"--- {path}\n{text}")
    assert res.ok or not res.failures
    assert not any(f.rule == "format" for f in res.failures)
