"""Subject outlines, best-fit similarity alignment, and outline distance.

Distances are divided by the subject's size, so they're comparable across drawings
photographed at different scales."""

import math
from dataclasses import dataclass

import cv2
import numpy as np

MIN_DRAWING_LUMINANCE = 140
_MIN_MASK, _MAX_MASK = 0.02, 0.95
_KEEP_FRACTION = 0.15


def _gray(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def drawing_media_ok(img: np.ndarray) -> bool:
    """Outline geometry assumes dark marks on light paper or a light canvas."""
    return float(np.median(_gray(img))) >= MIN_DRAWING_LUMINANCE


def _bounded(mask: np.ndarray) -> np.ndarray | None:
    frac = mask.mean()
    return mask if _MIN_MASK <= frac <= _MAX_MASK else None


def drawing_mask(img: np.ndarray) -> np.ndarray | None:
    """Filled silhouette of the drawn subject (bool), ignoring small stray marks."""
    gray = _gray(img)
    median = float(np.median(gray))
    otsu, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thresh = min(otsu, median - 40)
    marks = (gray <= thresh).astype(np.uint8) * 255
    if marks.mean() / 255 < 0.001:
        return None
    k = max(3, round(0.02 * max(gray.shape)))
    closed = cv2.morphologyEx(marks, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(closed)
    cv2.drawContours(filled, contours, -1, 255, cv2.FILLED)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(filled)
    if n <= 1:
        return None
    areas = stats[1:, cv2.CC_STAT_AREA]
    keep = [i + 1 for i, a in enumerate(areas) if a >= _KEEP_FRACTION * areas.max()]
    return _bounded(np.isin(labels, keep))


def photo_mask(img: np.ndarray) -> np.ndarray | None:
    """Subject mask for a reference photo cropped to roughly the subject (GrabCut)."""
    h, w = img.shape[:2]
    if min(h, w) < 20:
        return None
    dx, dy = max(1, round(0.04 * w)), max(1, round(0.04 * h))
    mask = np.zeros((h, w), np.uint8)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(img, mask, (dx, dy, w - 2 * dx, h - 2 * dy), bgd, fgd, 5, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        return None
    fg = np.isin(mask, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(fg)
    if n <= 1:
        return None
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return _bounded(labels == biggest)


def contour_points(mask: np.ndarray, n: int = 400) -> np.ndarray:
    """(n, 2) points evenly spaced along the largest outer contour, in pixels."""
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(contours, key=cv2.contourArea).reshape(-1, 2).astype(float)
    closed = np.vstack([c, c[:1]])
    seg = np.hypot(*np.diff(closed, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    t = np.linspace(0, cum[-1], n, endpoint=False)
    return np.column_stack([np.interp(t, cum, closed[:, 0]), np.interp(t, cum, closed[:, 1])])


@dataclass
class Similarity:
    scale: float
    angle_deg: float
    tx: float
    ty: float

    def matrix(self) -> np.ndarray:
        a = math.radians(self.angle_deg)
        c, s = self.scale * math.cos(a), self.scale * math.sin(a)
        return np.array([[c, -s, self.tx], [s, c, self.ty]])

    def apply(self, pts: np.ndarray) -> np.ndarray:
        m = self.matrix()
        return pts @ m[:, :2].T + m[:, 2]

    @staticmethod
    def from_matrix(m: np.ndarray) -> "Similarity":
        return Similarity(math.hypot(m[0, 0], m[1, 0]), math.degrees(math.atan2(m[1, 0], m[0, 0])), m[0, 2], m[1, 2])


def subject_size(pts: np.ndarray) -> float:
    """Square root of the outline's polygon area."""
    x, y = pts[:, 0], pts[:, 1]
    return math.sqrt(abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))) / 2)


def _nn(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For each point in a: distance to and index of its nearest point in b."""
    d2 = ((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
    idx = d2.argmin(axis=1)
    return np.sqrt(d2[np.arange(len(a)), idx]), idx


def _principal_angle(pts: np.ndarray) -> float:
    cov = np.cov((pts - pts.mean(axis=0)).T)
    vals, vecs = np.linalg.eigh(cov)
    v = vecs[:, np.argmax(vals)]
    return math.degrees(math.atan2(v[1], v[0]))


def _sym_error(a: np.ndarray, b: np.ndarray) -> float:
    return (_nn(a, b)[0].mean() + _nn(b, a)[0].mean()) / 2


def align(src: np.ndarray, dst: np.ndarray, iterations: int = 30) -> Similarity:
    """Best-fit similarity mapping src points onto dst points (moments init + ICP refinement)."""
    scale0 = subject_size(dst) / max(subject_size(src), 1e-9)
    d_angle = _principal_angle(dst) - _principal_angle(src)
    best: tuple[float, Similarity] | None = None
    for angle in (d_angle, d_angle + 180.0, 0.0):
        rot = Similarity(scale0, angle, 0.0, 0.0).apply(src)
        t = dst.mean(axis=0) - rot.mean(axis=0)
        sim = Similarity(scale0, angle, t[0], t[1])
        prev = math.inf
        for _ in range(iterations):
            _, idx = _nn(sim.apply(src), dst)
            m, _ = cv2.estimateAffinePartial2D(src.astype(np.float32), dst[idx].astype(np.float32), method=cv2.LMEDS)
            if m is None:
                break
            sim = Similarity.from_matrix(m)
            err = _sym_error(sim.apply(src), dst)
            if prev - err < 1e-3:
                break
            prev = err
        err = _sym_error(sim.apply(src), dst)
        if best is None or err < best[0]:
            best = (err, sim)
    return best[1]


def outline_distance(a: np.ndarray, b: np.ndarray, size: float, region: np.ndarray | None = None) -> float:
    """Symmetric mean nearest-point distance between outlines, divided by subject size.

    With `region` (a bool mask over a's points), only a's points inside it and b's points
    inside its padded bounding box count."""
    if region is None:
        return _sym_error(a, b) / size
    a_sel = a[region]
    if len(a_sel) == 0:
        return 0.0
    pad = 0.05 * size
    (x0, y0), (x1, y1) = a_sel.min(axis=0) - pad, a_sel.max(axis=0) + pad
    b_sel = b[(b[:, 0] >= x0) & (b[:, 0] <= x1) & (b[:, 1] >= y0) & (b[:, 1] <= y1)]
    terms = [_nn(a_sel, b)[0].mean()]
    if len(b_sel):
        terms.append(_nn(b_sel, a)[0].mean())
    return float(np.mean(terms)) / size
