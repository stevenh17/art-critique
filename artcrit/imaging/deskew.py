"""Find the sheet of paper in a phone photo and warp it flat."""

import math

import cv2
import numpy as np

Corners = tuple[tuple[float, float], ...]  # 4 points (x, y) in pixels: TL, TR, BR, BL

MIN_PAPER_AREA_FRACTION = 0.20


def _order(pts: np.ndarray) -> Corners:
    pts = pts.reshape(4, 2).astype(float)
    s = pts.sum(axis=1)
    d = pts[:, 1] - pts[:, 0]
    tl, br = pts[np.argmin(s)], pts[np.argmax(s)]
    tr, bl = pts[np.argmin(d)], pts[np.argmax(d)]
    return tuple((float(x), float(y)) for x, y in (tl, tr, br, bl))


def find_paper(img: np.ndarray) -> Corners | None:
    """Corners of the largest 4-sided bright region, or None if there isn't a plausible one."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    min_area = MIN_PAPER_AREA_FRACTION * img.shape[0] * img.shape[1]
    for c in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(c) < min_area:
            return None
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return _order(approx)
    return None


def full_corners(img: np.ndarray) -> Corners:
    h, w = img.shape[:2]
    return ((0.0, 0.0), (w - 1.0, 0.0), (w - 1.0, h - 1.0), (0.0, h - 1.0))


def warp(img: np.ndarray, corners: Corners, long_side: int = 1600) -> np.ndarray:
    """Perspective-warp the quad to an upright rectangle whose long side is `long_side`."""
    tl, tr, br, bl = corners
    width = (math.dist(tl, tr) + math.dist(bl, br)) / 2
    height = (math.dist(tl, bl) + math.dist(tr, br)) / 2
    scale = long_side / max(width, height)
    out_w, out_h = max(1, round(width * scale)), max(1, round(height * scale))
    src = np.array(corners, np.float32)
    dst = np.array([(0, 0), (out_w - 1, 0), (out_w - 1, out_h - 1), (0, out_h - 1)], np.float32)
    m = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, m, (out_w, out_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def normalize(img: np.ndarray) -> np.ndarray:
    """Gray-world white balance, then CLAHE on luminance."""
    f = img.astype(np.float32)
    means = f.reshape(-1, 3).mean(axis=0)
    f *= means.mean() / np.maximum(means, 1e-6)
    balanced = np.clip(f, 0, 255).astype(np.uint8)
    lab = cv2.cvtColor(balanced, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
