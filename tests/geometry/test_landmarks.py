import numpy as np
import pytest

from artcrit.cli import build_parser
from artcrit.config import Settings
from artcrit.geometry.landmarks import (
    IDX,
    FaceLandmarks,
    detect_face,
    face_ratios,
    landmark_error,
    landmarks_sane,
    model_path,
)


def synthetic_face(eye_y=0.45, mouth_y=0.78, eye_gap=0.12):
    """478 points; only the named ones matter. Face spans y 0.1 (forehead) to 0.9 (chin)."""
    pts = np.full((478, 2), 0.5)
    top, bottom = 0.1, 0.9
    at = lambda f: top + f * (bottom - top)  # noqa: E731
    pts[IDX["forehead"]] = (0.5, top)
    pts[IDX["chin"]] = (0.5, bottom)
    pts[IDX["l_brow"]] = (0.38, at(0.33))
    pts[IDX["r_brow"]] = (0.62, at(0.33))
    pts[IDX["l_eye_outer"]] = (0.5 - eye_gap / 2 - 0.1, at(eye_y))
    pts[IDX["l_eye_inner"]] = (0.5 - eye_gap / 2, at(eye_y))
    pts[IDX["r_eye_inner"]] = (0.5 + eye_gap / 2, at(eye_y))
    pts[IDX["r_eye_outer"]] = (0.5 + eye_gap / 2 + 0.1, at(eye_y))
    pts[IDX["nose_tip"]] = (0.5, at(0.6))
    pts[IDX["nose_base"]] = (0.5, at(0.63))
    pts[IDX["mouth_top"]] = (0.5, at(mouth_y - 0.01))
    pts[IDX["mouth_bottom"]] = (0.5, at(mouth_y + 0.01))
    return FaceLandmarks(pts)


def test_ratios_on_synthetic_points():
    r = face_ratios(synthetic_face())
    assert r["eye_line"] == pytest.approx(0.45, abs=0.01)
    assert r["mouth"] == pytest.approx(0.78, abs=0.01)
    assert r["eye_gap_over_eye_width"] == pytest.approx(0.12 / 0.1, rel=0.02)


def test_sanity_accepts_normal_face():
    assert landmarks_sane(synthetic_face())


def test_sanity_rejects_eyes_below_nose():
    assert not landmarks_sane(synthetic_face(eye_y=0.7))


def test_landmark_error_zero_for_same():
    assert all(v == pytest.approx(0) for v in landmark_error(synthetic_face(), synthetic_face()).values())


def test_landmark_error_flags_high_eyes():
    err = landmark_error(synthetic_face(eye_y=0.35), synthetic_face(eye_y=0.45))
    assert err["eye_line"] == pytest.approx(0.10, abs=0.01)


def test_detect_face_returns_none_without_model(tmp_path):
    assert detect_face(np.full((200, 200, 3), 255, np.uint8), tmp_path / "missing.task") is None


@pytest.mark.models
def test_detect_face_returns_none_on_blank_image():
    path = model_path(Settings())
    if not path.exists():
        pytest.skip("run `artcrit fetch-models` first")
    assert detect_face(np.full((300, 300, 3), 240, np.uint8), path) is None


def test_fetch_models_subcommand_parses():
    assert build_parser().parse_args(["fetch-models"]).command == "fetch-models"
