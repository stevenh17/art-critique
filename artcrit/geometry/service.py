"""One place that measures a drawing against its reference: outlines and faces, cached per pair."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from artcrit.geometry.landmarks import FaceLandmarks, detect_face, landmark_error, landmarks_sane
from artcrit.geometry.outline import (
    Similarity,
    align,
    contour_points,
    drawing_mask,
    drawing_media_ok,
    outline_distance,
    photo_mask,
    subject_size,
)
from artcrit.imaging.regions import Box, fit

WORK_SIDE = 800  # geometry runs on downscaled copies; results map back to full resolution
MIN_REGION_POINTS = 10


@dataclass
class Comparison:
    available: bool
    reason: str = ""
    sim: Similarity | None = None  # photo (work px) → drawing (work px)
    drawing_pts: np.ndarray | None = None  # drawing outline, work px
    photo_pts_in_drawing: np.ndarray | None = None  # photo outline mapped into drawing work px
    size: float = 0.0
    drawing_shape: tuple[int, int] = (0, 0)  # work (h, w)
    drawing_scale: float = 1.0  # full → work
    photo_scale: float = 1.0
    overall: float | None = None

    def region_distance(self, box: Box) -> float | None:
        if not self.available:
            return None
        h, w = self.drawing_shape
        x0, y0, x1, y1 = box
        pts = self.drawing_pts
        region = (pts[:, 0] >= x0 * w) & (pts[:, 0] <= x1 * w) & (pts[:, 1] >= y0 * h) & (pts[:, 1] <= y1 * h)
        if region.sum() < MIN_REGION_POINTS:
            return None
        return outline_distance(pts, self.photo_pts_in_drawing, self.size, region)

    def full_matrix(self) -> np.ndarray:
        """2×3 affine mapping full-resolution photo pixels to full-resolution drawing pixels."""
        m = np.vstack([self.sim.matrix(), [0, 0, 1]])
        to_work = np.diag([self.photo_scale, self.photo_scale, 1])
        from_work = np.diag([1 / self.drawing_scale, 1 / self.drawing_scale, 1])
        return (from_work @ m @ to_work)[:2]


@dataclass
class FaceComparison:
    available: bool
    reason: str = ""
    drawing: FaceLandmarks | None = None
    photo: FaceLandmarks | None = None
    error: dict[str, float] = field(default_factory=dict)


def _work(img: np.ndarray) -> tuple[np.ndarray, float]:
    small = fit(img, WORK_SIDE)
    return small, small.shape[1] / img.shape[1]


class Geometry:
    def __init__(self, model_path: Path | None, detector: Callable = detect_face):
        self.model_path = model_path
        self.detector = detector
        self._outline: dict = {}
        self._faces: dict = {}
        self._detected: dict = {}

    @staticmethod
    def _key(*arrays) -> tuple:
        return tuple(id(a) for a in arrays)

    def compare(self, drawing: np.ndarray, photo: np.ndarray) -> Comparison:
        key = self._key(drawing, photo)
        if key not in self._outline:
            self._outline[key] = (self._compare(drawing, photo), drawing, photo)  # keep arrays alive
        return self._outline[key][0]

    def _compare(self, drawing: np.ndarray, photo: np.ndarray) -> Comparison:
        if not drawing_media_ok(drawing):
            return Comparison(False, "drawing media too dark for outline measurement")
        d_small, d_scale = _work(drawing)
        p_small, p_scale = _work(photo)
        d_mask = drawing_mask(d_small)
        if d_mask is None:
            return Comparison(False, "no subject outline in drawing")
        p_mask = photo_mask(p_small)
        if p_mask is None:
            return Comparison(False, "no subject in photo")
        d_pts, p_pts = contour_points(d_mask), contour_points(p_mask)
        sim = align(p_pts, d_pts)
        mapped = sim.apply(p_pts)
        size = subject_size(d_pts)
        return Comparison(True, "", sim, d_pts, mapped, size, d_small.shape[:2], d_scale, p_scale,
                          outline_distance(d_pts, mapped, size))

    def _detect(self, img: np.ndarray) -> FaceLandmarks | None:
        key = id(img)
        if key not in self._detected:
            self._detected[key] = (self.detector(img, self.model_path), img)
        return self._detected[key][0]

    def faces(self, drawing: np.ndarray, photo: np.ndarray) -> FaceComparison:
        key = self._key(drawing, photo)
        if key not in self._faces:
            self._faces[key] = self._compare_faces(drawing, photo)
        return self._faces[key]

    def _compare_faces(self, drawing: np.ndarray, photo: np.ndarray) -> FaceComparison:
        d, p = self._detect(drawing), self._detect(photo)
        if d is None or p is None:
            return FaceComparison(False, "no face found in " + ("drawing" if d is None else "photo"), d, p)
        if not (landmarks_sane(d) and landmarks_sane(p)):
            return FaceComparison(False, "face landmarks failed the sanity check", d, p)
        return FaceComparison(True, "", d, p, landmark_error(d, p))
