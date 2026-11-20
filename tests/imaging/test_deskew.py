import math

import cv2
import numpy as np

from artcrit.imaging.deskew import find_paper, full_corners, normalize, warp

W, H = 800, 600
PAPER_W, PAPER_H = 400, 300


def _rotated_quad(angle_deg=12.0):
    cx, cy = W / 2, H / 2
    a = math.radians(angle_deg)
    pts = []
    for dx, dy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:  # TL TR BR BL
        x, y = dx * PAPER_W / 2, dy * PAPER_H / 2
        pts.append((cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)))
    return pts


def _scene(angle_deg=12.0):
    img = np.full((H, W, 3), 30, np.uint8)
    quad = _rotated_quad(angle_deg)
    cv2.fillPoly(img, [np.array(quad, np.int32)], (245, 245, 245))
    return img, quad


def test_find_paper_on_rotated_white_quad():
    img, quad = _scene()
    found = find_paper(img)
    assert found is not None
    for (fx, fy), (tx, ty) in zip(found, quad):
        assert math.hypot(fx - tx, fy - ty) < 10


def test_find_paper_returns_none_on_uniform_image():
    assert find_paper(np.full((H, W, 3), 128, np.uint8)) is None


def test_warp_produces_upright_rectangle():
    img, quad = _scene()
    out = warp(img, tuple(quad))
    h, w = out.shape[:2]
    assert max(h, w) == 1600
    assert abs((w / h) - (PAPER_W / PAPER_H)) / (PAPER_W / PAPER_H) < 0.03
    assert out.mean() > 200  # mostly paper, not background


def test_full_corners_matches_image_bounds():
    img = np.zeros((100, 200, 3), np.uint8)
    assert full_corners(img) == ((0.0, 0.0), (199.0, 0.0), (199.0, 99.0), (0.0, 99.0))


def test_normalize_keeps_shape_and_dtype():
    img, _ = _scene()
    out = normalize(img)
    assert out.shape == img.shape and out.dtype == np.uint8
