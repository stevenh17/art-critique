import cv2
import numpy as np
import pytest

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


def ellipse_drawing(h=600, w=480, axes=(140, 200), center=None, stretch_bottom=0.0, thickness=3, bg=245):
    """Black ellipse outline on light paper; optionally stretch the bottom part downward."""
    img = np.full((h, w, 3), bg, np.uint8)
    cx, cy = center or (w // 2, h // 2)
    pts = cv2.ellipse2Poly((cx, cy), axes, 0, 0, 360, 2).astype(float)
    # add a bump (an "ear") so the shape has no symmetry ambiguity
    bump = pts[:, 0] > cx + axes[0] * 0.9
    pts[bump, 0] += 25
    if stretch_bottom:
        below = pts[:, 1] > cy + axes[1] * 0.4
        pts[below, 1] += (pts[below, 1] - (cy + axes[1] * 0.4)) * stretch_bottom
    cv2.polylines(img, [pts.astype(np.int32)], True, (20, 20, 20), thickness)
    return img


def filled_area(img):
    m = drawing_mask(img)
    return int(m.sum()) if m is not None else 0


def test_media_ok_light_paper_true_dark_paper_false():
    assert drawing_media_ok(ellipse_drawing())
    assert not drawing_media_ok(ellipse_drawing(bg=110))


def test_drawing_mask_fills_outlined_ellipse():
    img = ellipse_drawing(axes=(140, 200))
    expected = np.zeros(img.shape[:2], np.uint8)
    cv2.ellipse(expected, (240, 300), (140, 200), 0, 0, 360, 1, -1)
    assert abs(filled_area(img) - expected.sum()) / expected.sum() < 0.10


def test_stray_far_blob_ignored():
    img = ellipse_drawing()
    base = filled_area(img)
    cv2.rectangle(img, (5, 570), (25, 580), (20, 20, 20), -1)
    assert abs(filled_area(img) - base) / base < 0.01


def test_drawing_mask_none_on_blank():
    assert drawing_mask(np.full((300, 300, 3), 245, np.uint8)) is None


def test_photo_mask_finds_dark_subject_on_light_background():
    img = np.full((400, 300, 3), 225, np.uint8)
    img += np.random.default_rng(0).integers(0, 10, img.shape, dtype=np.uint8)
    truth = np.zeros(img.shape[:2], np.uint8)
    cv2.ellipse(truth, (150, 200), (90, 140), 0, 0, 360, 1, -1)
    img[truth > 0] = (90, 110, 150)
    m = photo_mask(img)
    assert m is not None
    iou = (m & (truth > 0)).sum() / (m | (truth > 0)).sum()
    assert iou > 0.8


def test_align_recovers_known_similarity():
    src = contour_points(drawing_mask(ellipse_drawing()))
    true = Similarity(1.3, 12.0, 40.0, -25.0)
    est = align(src, true.apply(src))
    assert est.scale == pytest.approx(1.3, rel=0.03)
    assert abs(est.angle_deg - 12.0) < 2.0
    moved = est.apply(src)
    assert np.abs(moved - true.apply(src)).mean() < 3.0


def test_distance_zero_for_identical_and_positive_for_stretched():
    a = contour_points(drawing_mask(ellipse_drawing()))
    size = subject_size(a)
    assert outline_distance(a, a.copy(), size) < 0.005
    b = contour_points(drawing_mask(ellipse_drawing(stretch_bottom=0.5)))
    assert outline_distance(a, align(b, a).apply(b), size) > 0.02


def test_distance_invariant_to_how_drawing_was_photographed():
    ref = contour_points(drawing_mask(ellipse_drawing(stretch_bottom=0.3)))
    size = subject_size(ref)
    v_a = contour_points(drawing_mask(ellipse_drawing()))
    v_b = Similarity(0.7, 0.0, 60.0, 35.0).apply(v_a)  # same drawing, photographed smaller and shifted
    d_a = outline_distance(align(v_a, ref).apply(v_a), ref, size)
    d_b = outline_distance(align(v_b, ref).apply(v_b), ref, size)
    assert abs(d_a - d_b) < 0.005


def test_region_distance_isolates_bottom():
    a = contour_points(drawing_mask(ellipse_drawing()))
    b = contour_points(drawing_mask(ellipse_drawing(stretch_bottom=0.5)))
    b = align(b, a).apply(b)
    size = subject_size(a)
    top = a[:, 1] < np.percentile(a[:, 1], 30)
    bottom = a[:, 1] > np.percentile(a[:, 1], 70)
    assert outline_distance(a, b, size, bottom) > 2 * outline_distance(a, b, size, top)
