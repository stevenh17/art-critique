import json
from dataclasses import dataclass, field

import cv2
import numpy as np
import pytest

from artcrit.critic import CritiqueRun
from artcrit.critique_schema import parse_critique
from artcrit.engine.base import AgentResult, UsageLimitError
from artcrit.engine.fake import FakeEngine
from artcrit.geometry.service import Geometry
from artcrit.judge import JudgeResult
from artcrit.outcomes import (
    FIXED_RATIO,
    NOISE_FLOOR,
    GeometryMeasure,
    evaluate_revision,
    final_verdict,
    measure_issue,
    ratio_verdict,
)
from artcrit.store.images import ImageStore
from artcrit.store.sessions import SessionStore

from .geometry.test_landmarks import synthetic_face


@dataclass
class StubComp:
    available: bool = True
    region: float | None = 0.1
    overall: float | None = 0.1

    def region_distance(self, box):
        return self.region


@dataclass
class StubFaces:
    available: bool = False
    error: dict = field(default_factory=dict)
    drawing: object = None


def J(v):
    return JudgeResult(v, "r", "m")


def test_ratio_verdict_thresholds():
    assert ratio_verdict(1.0, 0.5, 0.6, 0.85) == "fixed"
    assert ratio_verdict(1.0, 0.8, 0.6, 0.85) == "partly"
    assert ratio_verdict(1.0, 0.9, 0.6, 0.85) == "not_fixed"


def test_geometry_overrides_only_proportion():
    geo = GeometryMeasure("outline", 0.10, 0.03, True)
    assert final_verdict("proportion", J("not_fixed"), geo) == ("fixed", "geometry:outline", True)
    assert final_verdict("values", J("not_fixed"), geo) == ("not_fixed", "judge", True)


def test_disagreement_flagged_even_without_override():
    geo = GeometryMeasure("outline", 0.10, 0.10, True)
    assert final_verdict("edges", J("fixed"), geo)[2] is True


def test_not_confident_geometry_never_overrides():
    geo = GeometryMeasure("outline", 0.01, 0.0, False)
    assert final_verdict("proportion", J("partly"), geo) == ("partly", "judge", False)


def test_noise_floor_makes_unmeasurable():
    m = measure_issue((0, 0, 1, 1), StubComp(region=NOISE_FLOOR / 2), StubComp(region=0.0), StubFaces(), StubFaces())
    assert m is not None and not m.confident


def test_outline_measure_when_both_available():
    m = measure_issue((0, 0, 1, 1), StubComp(region=0.1), StubComp(region=0.1 * FIXED_RATIO), StubFaces(), StubFaces())
    assert (m.source, m.confident, m.old, m.new) == ("outline", True, 0.1, pytest.approx(0.06))


def test_unavailable_geometry_gives_none():
    assert measure_issue((0, 0, 1, 1), StubComp(available=False), StubComp(), StubFaces(), StubFaces()) is None


def test_landmarks_preferred_over_outline_when_available():
    face = synthetic_face()
    old = StubFaces(True, {"eye_line": 0.10, "mouth": 0.0, "brow": 0, "nose_base": 0, "eye_gap_over_eye_width": 0}, face)
    new = StubFaces(True, {"eye_line": 0.02, "mouth": 0.0, "brow": 0, "nose_base": 0, "eye_gap_over_eye_width": 0}, face)
    eye_box = (0.2, 0.4, 0.8, 0.55)  # eyes (eye_line and eye spacing) sit at y ≈ 0.46; brow at 0.36 is outside
    m = measure_issue(eye_box, StubComp(), StubComp(), old, new)
    assert m.source == "landmarks" and m.old == pytest.approx(0.05) and m.new == pytest.approx(0.01)


# ---- evaluate_revision against the real store ----
CRIT = json.dumps({"issues": [
    {"category": "proportion", "title": "Jaw too long", "instruction": "Shorten.", "drawing_cells": ["D7", "E7"], "photo_cells": ["D7"]},
    {"category": "values", "title": "Shadow light", "instruction": "Darken.", "drawing_cells": ["B3"], "photo_cells": ["B3"]}]})


def face_img(jaw=0):
    img = np.full((640, 480, 3), 245, np.uint8)
    cv2.ellipse(img, (240, 300 + jaw // 2), (150, 200 + jaw // 2), 0, 0, 360, (30, 30, 30), 3)
    return img


@pytest.fixture
def two_versions(tmp_path):
    store, images = SessionStore(tmp_path / "s.db"), ImageStore(tmp_path / "img")
    photo = np.full((640, 480, 3), 220, np.uint8)
    cv2.ellipse(photo, (240, 300), (150, 200), 0, 0, 360, (90, 100, 140), -1)
    d = store.add_drawing(images.save(photo, "photo"), (0, 0, 1, 1), "https://x", "CC0", True)
    c = ((0, 0), (1, 0), (1, 1), (0, 1))
    s1 = store.add_submission(d, 1, None, "o", images.save(face_img(jaw=90), "drawing"), c)
    ids = store.add_critique(s1, CritiqueRun(parse_critique(CRIT), [], "m", "sha"))
    s2 = store.add_submission(d, 2, s1, "o", images.save(face_img(jaw=0), "drawing"), c)
    return store, images, s1, s2, ids


def judge_reply(v):
    return lambda tools: AgentResult(json.dumps({"verdict": v, "reason": "r"}), [], "m")


def test_evaluate_revision_judges_each_issue(two_versions):
    store, images, s1, s2, ids = two_versions
    eng = FakeEngine([judge_reply("partly"), judge_reply("not_fixed")])
    res = evaluate_revision(store.get_submission(s1), store.get_submission(s2), images, eng, Geometry(None, detector=lambda i, m: None))
    assert [o.issue_id for o in res.outcomes] == ids
    assert res.outcomes[1].final_verdict == "not_fixed" and res.outcomes[1].source == "judge"
    assert res.overall_old is not None and res.overall_new < res.overall_old  # jaw got closer to the photo


def test_intentional_issue_skipped_no_judge_call(two_versions):
    store, images, s1, s2, ids = two_versions
    store.add_event("intentional", issue_id=ids[0])
    eng = FakeEngine([judge_reply("fixed")])
    res = evaluate_revision(store.get_submission(s1), store.get_submission(s2), images, eng, None)
    assert [o.issue_id for o in res.outcomes] == [ids[1]] and len(eng.calls) == 1


def test_garbage_judge_gives_cant_tell_row(two_versions):
    store, images, s1, s2, ids = two_versions
    garbage = lambda tools: AgentResult("???", [], "m")  # noqa: E731
    eng = FakeEngine([garbage, garbage, judge_reply("fixed")])
    res = evaluate_revision(store.get_submission(s1), store.get_submission(s2), images, eng, None)
    assert res.outcomes[0].judge_verdict == "cant_tell" and res.outcomes[0].final_verdict == "cant_tell"


def test_usage_limit_propagates_from_judge(two_versions):
    store, images, s1, s2, _ = two_versions

    def boom(tools):
        raise UsageLimitError("x")

    with pytest.raises(UsageLimitError):
        evaluate_revision(store.get_submission(s1), store.get_submission(s2), images, FakeEngine([boom]), None)
