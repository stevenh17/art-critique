"""'Help me measure': six points the artist clicks on the photo and both drawing versions."""

import cv2
import numpy as np

from artcrit.imaging.regions import Box
from artcrit.outcomes import GeometryMeasure

POINTS_NOISE = 0.05  # typical click imprecision, as a fraction of eye-to-eye distance
POINT_NAMES = ("left eye outer corner", "right eye outer corner", "nose tip", "chin", "hairline centre", "mouth centre")


def points_error(drawing_px: np.ndarray, photo_px: np.ndarray) -> np.ndarray:
    """Per-point error after the best similarity fit of photo points onto drawing points,
    as a fraction of the drawing's eye-to-eye distance. The robust fit lets one wrong point stand out."""
    d, p = np.asarray(drawing_px, np.float32), np.asarray(photo_px, np.float32)
    m, _ = cv2.estimateAffinePartial2D(p, d, method=cv2.LMEDS)
    if m is None:
        m, _ = cv2.estimateAffinePartial2D(p, d)
    mapped = p @ m[:, :2].T + m[:, 2]
    eye = max(float(np.linalg.norm(d[0] - d[1])), 1e-6)
    return np.linalg.norm(mapped - d, axis=1) / eye


def measure_from_points(issue_box: Box, old_px: np.ndarray, new_px: np.ndarray, photo_px: np.ndarray,
                        old_shape: tuple[int, ...]) -> GeometryMeasure:
    h, w = old_shape[:2]
    norm = np.asarray(old_px, float) / (w, h)
    sel = (norm[:, 0] >= issue_box[0]) & (norm[:, 0] <= issue_box[2]) & (norm[:, 1] >= issue_box[1]) & (norm[:, 1] <= issue_box[3])
    if not sel.any():
        sel = np.ones(len(norm), bool)
    old = float(points_error(old_px, photo_px)[sel].mean())
    new = float(points_error(new_px, photo_px)[sel].mean())
    return GeometryMeasure("points", old, new, old > POINTS_NOISE)
