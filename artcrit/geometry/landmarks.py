"""Face landmarks (MediaPipe Face Landmarker), proportion ratios, and a sanity check."""

import functools
import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
)
IDX = {
    "forehead": 10, "chin": 152, "l_eye_outer": 33, "l_eye_inner": 133, "r_eye_inner": 362, "r_eye_outer": 263,
    "nose_tip": 1, "nose_base": 2, "mouth_top": 13, "mouth_bottom": 14, "l_brow": 105, "r_brow": 334,
}


def model_path(settings) -> Path:
    return Path(settings.data_dir) / "models" / "face_landmarker.task"


def fetch_model(settings) -> Path:
    path = model_path(settings)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.rename(path)
    return path


@dataclass
class FaceLandmarks:
    points: np.ndarray  # (N, 2), normalized to [0, 1] of the image

    def p(self, name: str) -> np.ndarray:
        return self.points[IDX[name]]


@functools.lru_cache(maxsize=2)
def _landmarker(path: str):
    from mediapipe.tasks.python import BaseOptions, vision

    opts = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=path), num_faces=1,
        min_face_detection_confidence=0.5, min_face_presence_confidence=0.5,
    )
    return vision.FaceLandmarker.create_from_options(opts)


def detect_face(img: np.ndarray, model: Path) -> FaceLandmarks | None:
    """Landmarks of the single most prominent face, or None. Never raises."""
    if not Path(model).is_file():
        return None
    try:
        import mediapipe as mp

        rgb = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        result = _landmarker(str(model)).detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    except Exception:  # model or runtime problems mean "unavailable", not a crash
        log.exception("face detection failed")
        return None
    if not result.face_landmarks:
        return None
    return FaceLandmarks(np.array([(lm.x, lm.y) for lm in result.face_landmarks[0]], dtype=float))


def _axis_t(lm: FaceLandmarks, p: np.ndarray) -> float:
    """Position of p along the forehead (0) → chin (1) axis."""
    f, c = lm.p("forehead"), lm.p("chin")
    v = c - f
    return float(np.dot(p - f, v) / max(np.dot(v, v), 1e-12))


def _eye_centres(lm: FaceLandmarks) -> tuple[np.ndarray, np.ndarray]:
    return (lm.p("l_eye_outer") + lm.p("l_eye_inner")) / 2, (lm.p("r_eye_outer") + lm.p("r_eye_inner")) / 2


def face_ratios(lm: FaceLandmarks) -> dict[str, float]:
    le, re = _eye_centres(lm)
    eye_w = (np.linalg.norm(lm.p("l_eye_outer") - lm.p("l_eye_inner")) +
             np.linalg.norm(lm.p("r_eye_outer") - lm.p("r_eye_inner"))) / 2
    return {
        "eye_line": _axis_t(lm, (le + re) / 2),
        "brow": _axis_t(lm, (lm.p("l_brow") + lm.p("r_brow")) / 2),
        "nose_base": _axis_t(lm, lm.p("nose_base")),
        "mouth": _axis_t(lm, (lm.p("mouth_top") + lm.p("mouth_bottom")) / 2),
        "eye_gap_over_eye_width": float(np.linalg.norm(lm.p("l_eye_inner") - lm.p("r_eye_inner")) / max(eye_w, 1e-12)),
    }


# Where each ratio's feature sits, for matching ratios to an issue region.
RATIO_FEATURES = {
    "eye_line": ("l_eye_outer", "l_eye_inner", "r_eye_inner", "r_eye_outer"),
    "brow": ("l_brow", "r_brow"),
    "nose_base": ("nose_base",),
    "mouth": ("mouth_top", "mouth_bottom"),
    "eye_gap_over_eye_width": ("l_eye_inner", "r_eye_inner"),
}


def landmarks_sane(lm: FaceLandmarks) -> bool:
    f, c = lm.p("forehead"), lm.p("chin")
    if np.linalg.norm(c - f) < 0.10:
        return False
    r = face_ratios(lm)
    if not (0 < r["brow"] < r["eye_line"] < r["nose_base"] < r["mouth"] < 1):
        return False
    v = c - f
    side = lambda p: np.sign(v[0] * (p[1] - f[1]) - v[1] * (p[0] - f[0]))  # noqa: E731
    le, re = _eye_centres(lm)
    return side(le) != side(re) and side(le) != 0


def landmark_error(drawing: FaceLandmarks, photo: FaceLandmarks) -> dict[str, float]:
    d, p = face_ratios(drawing), face_ratios(photo)
    return {k: abs(d[k] - p[k]) for k in d}
