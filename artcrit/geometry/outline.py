"""Subject lines, best-fit similarity alignment, and line distance.

The drawing is reduced to its pencil lines and the photo to its strong edges. Neither is
filled into a silhouette: open strokes (shoulders, collars) count, and the two images may
show different amounts of the subject. Alignment is a two-way truncated chamfer match:
drawn lines should sit on photo edges, and photo edges should sit on drawn lines; points
with no counterpart cost a fixed amount instead of dragging the fit.

Distances are divided by the subject's size, so they're comparable across drawings
photographed at different scales."""

import math
from dataclasses import dataclass

import cv2
import numpy as np

MIN_DRAWING_LUMINANCE = 140
MAX_ROTATION_DEG = 12.0  # drawings are deskewed and photos cropped upright
SCALE_RANGE = (0.6, 1.6)  # around the ratio of the two subjects' bounding boxes
SHIFT_RANGE = 0.25  # coarse search, as a fraction of the drawing's subject size
TRUNCATE = 0.08  # chamfer and distance cap, as a fraction of subject size
MAX_POINTS = 1200
MIN_LINE_FRACTION = 0.001  # fewer line pixels than this means there's nothing to measure
_MIN_COMPONENT = 0.0004  # drop specks smaller than this fraction of the image
MAX_FIT_COST = 0.35  # mean truncated chamfer cost above this (fraction of TRUNCATE): no confident fit


def _gray(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def drawing_media_ok(img: np.ndarray) -> bool:
    """Line extraction assumes dark marks on light paper or a light canvas."""
    return float(np.median(_gray(img))) >= MIN_DRAWING_LUMINANCE


def _drop_specks(mask: np.ndarray) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= _MIN_COMPONENT * mask.size
    return keep[labels]


def _enough(mask: np.ndarray) -> np.ndarray | None:
    return mask if mask.mean() >= MIN_LINE_FRACTION else None


def drawing_lines(img: np.ndarray) -> np.ndarray | None:
    """Pencil marks (bool), measured against the local paper tone so uneven lighting doesn't count."""
    gray = _gray(img)
    paper = cv2.GaussianBlur(gray, (0, 0), max(gray.shape) / 30)
    darker = paper.astype(np.int16) - gray.astype(np.int16)
    marks = darker > max(12.0, 0.35 * float(np.percentile(darker, 99)))
    return _enough(_drop_specks(marks))


def photo_edges(img: np.ndarray) -> np.ndarray | None:
    """Strong edges in the reference photo (bool)."""
    blurred = cv2.GaussianBlur(_gray(img), (0, 0), 1.5)
    v = float(np.median(blurred))
    edges = cv2.Canny(blurred, 0.33 * v, 0.66 * v + 20) > 0
    return _enough(_drop_specks(edges))


def line_points(mask: np.ndarray, n: int = MAX_POINTS) -> np.ndarray:
    """Up to n (x, y) points spread over the mask's pixels, in a fixed order (deterministic)."""
    ys, xs = np.nonzero(mask)
    pts = np.column_stack([xs, ys]).astype(float)
    if len(pts) > n:
        pts = pts[np.linspace(0, len(pts) - 1, n).round().astype(int)]
    return pts


def subject_size(pts: np.ndarray) -> float:
    """Square root of the points' bounding-box area."""
    span = pts.max(axis=0) - pts.min(axis=0) + 1
    return math.sqrt(float(span[0] * span[1]))


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

    def inverse(self) -> "Similarity":
        return Similarity.from_matrix(cv2.invertAffineTransform(self.matrix()))

    @staticmethod
    def from_matrix(m: np.ndarray) -> "Similarity":
        return Similarity(math.hypot(m[0, 0], m[1, 0]), math.degrees(math.atan2(m[1, 0], m[0, 0])), m[0, 2], m[1, 2])


class _Field:
    """Truncated distance to the nearest line pixel, looked up for many points at once."""

    def __init__(self, mask: np.ndarray, cap: float):
        self.cap = cap
        self.dist = np.minimum(cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5), cap)
        self.h, self.w = mask.shape

    def at(self, pts: np.ndarray) -> np.ndarray:
        """pts (..., 2) → distances (...); points off the image cost the cap."""
        x, y = np.rint(pts[..., 0]).astype(int), np.rint(pts[..., 1]).astype(int)
        inside = (x >= 0) & (x < self.w) & (y >= 0) & (y < self.h)
        out = np.full(x.shape, self.cap, np.float32)
        out[inside] = self.dist[y[inside], x[inside]]
        return out


def align(photo_mask: np.ndarray, drawing_mask: np.ndarray) -> tuple[Similarity, float]:
    """Best-fit similarity mapping photo pixels onto drawing pixels, and its cost.

    The cost is the mean truncated two-way chamfer distance as a fraction of the cap: 0 is a
    perfect fit, 1 means no line found a counterpart."""
    p_pts, d_pts = line_points(photo_mask), line_points(drawing_mask)
    d_size, p_size = subject_size(d_pts), subject_size(p_pts)
    cap = TRUNCATE * d_size
    to_drawing, to_photo = _Field(drawing_mask, cap), _Field(photo_mask, cap * p_size / d_size)
    d_mid, p_mid = d_pts.mean(axis=0), p_pts.mean(axis=0)

    def costs(scale, angle, shifts):
        """Cost for one scale and angle at many shifts (k, 2) of the photo's centre in the drawing."""
        m = Similarity(scale, angle, 0.0, 0.0).matrix()[:, :2]
        p_rot = (p_pts - p_mid) @ m.T
        fwd = to_drawing.at(p_rot[None] + shifts[:, None]).mean(axis=1) / to_drawing.cap
        inv = np.linalg.inv(m)
        d_back = (d_pts[None] - shifts[:, None]) @ inv.T + p_mid
        back = to_photo.at(d_back).mean(axis=1) / to_photo.cap
        return (fwd + back) / 2

    def sim_of(scale, angle, shift):
        m = Similarity(scale, angle, 0.0, 0.0).matrix()[:, :2]
        t = shift - m @ p_mid
        return Similarity(scale, angle, float(t[0]), float(t[1]))

    grid = np.linspace(-SHIFT_RANGE, SHIFT_RANGE, 11) * d_size
    shifts = d_mid + np.stack(np.meshgrid(grid, grid), axis=-1).reshape(-1, 2)
    best = (math.inf, 1.0, 0.0, d_mid)
    for scale in np.geomspace(*SCALE_RANGE, 11) * d_size / p_size:
        for angle in np.arange(-MAX_ROTATION_DEG, MAX_ROTATION_DEG + 1e-9, 2.0):
            c = costs(scale, angle, shifts)
            i = int(np.argmin(c))
            if c[i] < best[0]:
                best = (float(c[i]), scale, float(angle), shifts[i])

    # Refine by shrinking coordinate steps (the cost is piecewise constant, so no gradients).
    cost, scale, angle, shift = best
    steps = [0.03 * scale, 1.0, 0.01 * d_size]
    while steps[1] > 0.05:
        improved = False
        for k in range(3):
            for sign in (1, -1):
                s, a, t = scale, angle, shift.copy()
                if k == 0:
                    s = scale + sign * steps[0]
                elif k == 1:
                    a = float(np.clip(angle + sign * steps[1], -MAX_ROTATION_DEG, MAX_ROTATION_DEG))
                else:
                    trial = np.array([t + (sign * steps[2], 0), t + (0, sign * steps[2])])
                    c = costs(s, a, trial)
                    j = int(np.argmin(c))
                    if c[j] < cost:
                        cost, shift, improved = float(c[j]), trial[j], True
                    continue
                c = float(costs(s, a, t[None])[0])
                if c < cost:
                    cost, scale, angle, improved = c, s, a, True
        if not improved:
            steps = [x / 2 for x in steps]
    return sim_of(scale, angle, shift), cost


def line_distance(a: np.ndarray, b: np.ndarray, size: float, region: np.ndarray | None = None) -> float:
    """Mean distance from a's points (optionally only those in `region`) to the nearest of b's,
    capped per point at TRUNCATE·size and divided by size.

    One-way on purpose: a is the drawing, b the photo's edges. Photo detail the artist chose
    not to draw (texture, folds) must not count as an error."""
    sel = a if region is None else a[region]
    if len(sel) == 0:
        return 0.0
    d2 = ((sel[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
    nearest = np.sqrt(d2.min(axis=1))
    return float(np.minimum(nearest, TRUNCATE * size).mean()) / size
