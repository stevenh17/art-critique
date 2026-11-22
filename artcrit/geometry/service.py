"""One place that measures a drawing against its reference: outlines and faces, cached per pair."""

import hashlib
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from artcrit.geometry.landmarks import FaceLandmarks, detect_face, landmark_error, landmarks_sane
from artcrit.geometry.outline import (
    MAX_FIT_COST,
    Similarity,
    align,
    drawing_lines,
    drawing_media_ok,
    line_distance,
    line_points,
    photo_edges,
    subject_size,
)
from artcrit.imaging.regions import Box, fit

WORK_SIDE = 400  # geometry runs on downscaled copies; results map back to full resolution
MIN_REGION_POINTS = 10
CACHE_SIZE = 16  # results only (never images), keyed by pixel content


def _digest(img: np.ndarray) -> str:
    return hashlib.blake2b(np.ascontiguousarray(img).data, digest_size=16).hexdigest() + str(img.shape)


class _LRU(OrderedDict):
    def get_or(self, key, make):
        if key in self:
            self.move_to_end(key)
            return self[key]
        value = self[key] = make()
        while len(self) > CACHE_SIZE:
            self.popitem(last=False)
        return value


@dataclass
class Comparison:
    available: bool
    reason: str = ""
    sim: Similarity | None = None  # photo (work px) → drawing (work px)
    drawing_pts: np.ndarray | None = None  # drawn line points, work px
    photo_pts_in_drawing: np.ndarray | None = None  # photo edge points mapped into drawing work px
    size: float = 0.0
    drawing_shape: tuple[int, int] = (0, 0)  # work (h, w)
    drawing_scale: float = 1.0  # full → work
    photo_scale: float = 1.0
    overall: float | None = None
    fit_cost: float | None = None  # 0 = every line found a counterpart, 1 = none did

    def region_distance(self, box: Box) -> float | None:
        if not self.available:
            return None
        h, w = self.drawing_shape
        x0, y0, x1, y1 = box
        pts = self.drawing_pts
        region = (pts[:, 0] >= x0 * w) & (pts[:, 0] <= x1 * w) & (pts[:, 1] >= y0 * h) & (pts[:, 1] <= y1 * h)
        if region.sum() < MIN_REGION_POINTS:
            return None
        return line_distance(pts, self.photo_pts_in_drawing, self.size, region)

    def full_matrix(self) -> np.ndarray:
        """2×3 affine mapping full-resolution photo pixels to full-resolution drawing pixels."""
        m = np.vstack([self.sim.matrix(), [0, 0, 1]])
        to_work = np.diag([self.photo_scale, self.photo_scale, 1])
        from_work = np.diag([1 / self.drawing_scale, 1 / self.drawing_scale, 1])
        return (from_work @ m @ to_work)[:2]


def map_box(box: Box, old: Comparison, new: Comparison) -> Box:
    """Carry a box on the old drawing to the matching place on the new drawing, via the photo.
    Returns the box unchanged when either version couldn't be aligned."""
    if not (old.available and new.available and old.sim is not None and new.sim is not None):
        return box
    (oh, ow), (nh, nw) = old.drawing_shape, new.drawing_shape
    x0, y0, x1, y1 = box
    corners = np.array([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]) * (ow, oh)
    m = np.vstack([old.sim.matrix(), [0, 0, 1]])
    in_photo = (np.linalg.inv(m) @ np.c_[corners, np.ones(4)].T).T[:, :2]
    mapped = new.sim.apply(in_photo) / (nw, nh)
    lo, hi = np.clip(mapped.min(axis=0), 0, 1), np.clip(mapped.max(axis=0), 0, 1)
    return (float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1]))


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
        self._outline, self._faces, self._detected = _LRU(), _LRU(), _LRU()

    def compare(self, drawing: np.ndarray, photo: np.ndarray) -> Comparison:
        def make():
            try:
                return self._compare(drawing, photo)
            except Exception as e:  # measurement is best-effort; never take down a critique
                return Comparison(False, f"measurement error ({type(e).__name__})")

        return self._outline.get_or((_digest(drawing), _digest(photo)), make)

    def _compare(self, drawing: np.ndarray, photo: np.ndarray) -> Comparison:
        if not drawing_media_ok(drawing):
            return Comparison(False, "drawing media too dark for outline measurement")
        d_small, d_scale = _work(drawing)
        p_small, p_scale = _work(photo)
        d_lines = drawing_lines(d_small)
        if d_lines is None:
            return Comparison(False, "no subject outline in drawing")
        p_edges = photo_edges(p_small)
        if p_edges is None:
            return Comparison(False, "no subject in photo")
        sim, cost = align(p_edges, d_lines)
        if cost > MAX_FIT_COST:
            return Comparison(False, "couldn't match the drawing's lines to the photo", fit_cost=cost)
        d_pts = line_points(d_lines)
        mapped = sim.apply(line_points(p_edges))
        size = subject_size(d_pts)
        return Comparison(True, "", sim, d_pts, mapped, size, d_small.shape[:2], d_scale, p_scale,
                          line_distance(d_pts, mapped, size), cost)

    def _detect(self, img: np.ndarray) -> FaceLandmarks | None:
        return self._detected.get_or(_digest(img), lambda: self.detector(img, self.model_path))

    def faces(self, drawing: np.ndarray, photo: np.ndarray) -> FaceComparison:
        def make():
            try:
                return self._compare_faces(drawing, photo)
            except Exception as e:
                return FaceComparison(False, f"measurement error ({type(e).__name__})")

        return self._faces.get_or((_digest(drawing), _digest(photo)), make)

    def _compare_faces(self, drawing: np.ndarray, photo: np.ndarray) -> FaceComparison:
        d, p = self._detect(drawing), self._detect(photo)
        if d is None or p is None:
            return FaceComparison(False, "no face found in " + ("drawing" if d is None else "photo"), d, p)
        if not (landmarks_sane(d) and landmarks_sane(p)):
            return FaceComparison(False, "face landmarks failed the sanity check", d, p)
        return FaceComparison(True, "", d, p, landmark_error(d, p))
