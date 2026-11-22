import math

import cv2
import numpy as np
import pytest

from artcrit.geometry.outline import (
    MAX_ROTATION_DEG,
    Similarity,
    align,
    drawing_lines,
    drawing_media_ok,
    line_distance,
    line_points,
    photo_edges,
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


# A head-and-shoulders figure in "figure units"; drawn as open pencil lines, or rendered as a photo.
EYES = np.array([(-38.0, -10.0), (38.0, -10.0)])
HEAD = ((0, 0), (80, 105))


def _to(pts, sim: Similarity):
    return sim.apply(np.asarray(pts, float)).astype(np.int32)


def figure_drawing(sim=Similarity(1.6, 0.0, 240.0, 230.0), h=640, w=480, chin_drop=0.0):
    """Pencil sketch: closed head, open shoulder strokes that never close into a shape, eyes, mouth."""
    img = np.full((h, w, 3), 238, np.uint8)
    img += np.random.default_rng(3).integers(0, 6, img.shape, dtype=np.uint8)  # paper grain
    head = cv2.ellipse2Poly(*HEAD, 0, 0, 360, 4).astype(float)
    head[head[:, 1] > 40, 1] += chin_drop
    cv2.polylines(img, [_to(head, sim)], True, (60, 60, 60), 2, cv2.LINE_AA)
    cv2.polylines(img, [_to([(-150, 190), (-95, 130), (-40, 105)], sim)], False, (60, 60, 60), 2, cv2.LINE_AA)
    cv2.polylines(img, [_to([(40, 105), (95, 130), (150, 190)], sim)], False, (60, 60, 60), 2, cv2.LINE_AA)
    for e in EYES:
        cv2.polylines(img, [_to([e - (14, 0), e + (0, -5), e + (14, 0)], sim)], False, (50, 50, 50), 2)
    cv2.polylines(img, [_to([(-18, 55), (18, 55)], sim)], False, (60, 60, 60), 2)
    return img


def figure_photo(sim=Similarity(1.0, 0.0, 220.0, 170.0), h=420, w=440):
    """Photo on a dark background, showing a torso the drawing leaves out."""
    img = np.full((h, w, 3), 50, np.uint8)
    torso = [(-170, 400), (-150, 190), (-95, 130), (-40, 105), (40, 105), (95, 130), (150, 190), (170, 400)]
    cv2.fillPoly(img, [_to(torso, sim)], (110, 120, 150))
    cv2.fillPoly(img, [_to(cv2.ellipse2Poly(*HEAD, 0, 0, 360, 4), sim)], (170, 190, 215))
    for e in EYES:
        cv2.ellipse(img, tuple(_to([e], sim)[0]), (int(12 * sim.scale), int(6 * sim.scale)), sim.angle_deg,
                    0, 360, (40, 40, 40), -1)
    cv2.line(img, *[tuple(p) for p in _to([(-18, 55), (18, 55)], sim)], (60, 50, 120), 3)
    return img


def test_media_ok_light_paper_true_dark_paper_false():
    assert drawing_media_ok(ellipse_drawing())
    assert not drawing_media_ok(ellipse_drawing(bg=110))


def test_drawing_lines_follow_the_stroke():
    lines = drawing_lines(ellipse_drawing(axes=(140, 200)))
    ys, xs = np.nonzero(lines)
    r = np.hypot((xs - 240) / 140, (ys - 300) / 200)
    assert np.median(np.abs(r - 1)) < 0.03


def test_open_strokes_count_as_lines():
    lines = drawing_lines(figure_drawing())
    shoulder = _to([(-120, 160)], Similarity(1.6, 0.0, 240.0, 230.0))[0]
    x, y = shoulder
    assert lines[y - 12:y + 12, x - 12:x + 12].any()


def test_stray_speck_ignored():
    img = ellipse_drawing()
    cv2.circle(img, (20, 575), 1, (20, 20, 20), -1)
    assert not drawing_lines(img)[570:580, 15:25].any()


def test_drawing_lines_none_on_blank_paper_with_uneven_light():
    shade = np.linspace(200, 250, 300).astype(np.uint8)
    img = np.dstack([np.tile(shade, (300, 1))] * 3)
    assert drawing_lines(img) is None


def test_photo_edges_find_subject_boundary():
    edges = photo_edges(figure_photo())
    assert edges is not None
    ys, xs = np.nonzero(edges)
    assert len(xs) > 300


def _eyes_in_drawing(photo_sim, fit: Similarity):
    return fit.apply(photo_sim.apply(EYES))


@pytest.mark.parametrize("photo_sim", [Similarity(1.0, 0.0, 220.0, 170.0), Similarity(0.8, 7.0, 200.0, 150.0)])
def test_align_open_line_drawing_to_photo_with_extra_torso(photo_sim):
    """Regression: the silhouette method matched the drawn head to the photo's head-and-torso and
    tilted the overlay. Lines must line the eyes up regardless of what else the photo shows."""
    d_sim = Similarity(1.6, 0.0, 240.0, 230.0)
    fit, cost = align(photo_edges(figure_photo(photo_sim)), drawing_lines(figure_drawing(d_sim)))
    assert cost < 0.3
    err = np.hypot(*(_eyes_in_drawing(photo_sim, fit) - d_sim.apply(EYES)).T)
    assert err.max() < 0.06 * 1.6 * 76  # within 6% of the eye spacing
    assert abs(fit.angle_deg + photo_sim.angle_deg) < 3


def test_align_recovers_known_similarity():
    d_lines = drawing_lines(ellipse_drawing())
    true = Similarity(0.8, 6.0, 40.0, -25.0)  # photo → drawing
    photo = cv2.warpAffine(ellipse_drawing(), cv2.invertAffineTransform(true.matrix()), (480, 600),
                           borderValue=(245, 245, 245))
    fit, _ = align(photo_edges(photo), d_lines)
    assert fit.scale == pytest.approx(0.8, rel=0.04)
    assert abs(fit.angle_deg - 6.0) < 2.0


def test_align_symmetric_oval_stays_upright():
    img = np.full((600, 480, 3), 245, np.uint8)
    cv2.ellipse(img, (240, 300), (140, 200), 0, 0, 360, (20, 20, 20), 3)
    fit, _ = align(photo_edges(img), drawing_lines(img))
    assert abs(fit.angle_deg) <= MAX_ROTATION_DEG and abs(fit.angle_deg) < 3


def test_unrelated_photo_fits_badly():
    sq = np.full((480, 440, 3), 200, np.uint8)
    cv2.rectangle(sq, (100, 120), (340, 360), (40, 60, 90), -1)
    _, good = align(photo_edges(figure_photo()), drawing_lines(figure_drawing()))
    _, bad = align(photo_edges(sq), drawing_lines(figure_drawing()))
    assert bad > good + 0.15


def test_distance_zero_for_identical_and_positive_for_stretched():
    a = line_points(drawing_lines(ellipse_drawing()))
    size = subject_size(a)
    assert line_distance(a, a.copy(), size) < 0.005
    b = line_points(drawing_lines(ellipse_drawing(stretch_bottom=0.5)))
    assert line_distance(b, a, size) > 0.02


def test_distance_ignores_photo_detail_that_was_not_drawn():
    a = line_points(drawing_lines(ellipse_drawing()))
    size = subject_size(a)
    extra = np.column_stack([np.linspace(200, 280, 200), np.full(200, 300.0)])  # a crease inside the face
    assert line_distance(a, np.vstack([a, extra]), size) < 0.005


def test_region_distance_isolates_bottom():
    a = line_points(drawing_lines(ellipse_drawing(stretch_bottom=0.5)))
    b = line_points(drawing_lines(ellipse_drawing()))
    size = subject_size(a)
    top = a[:, 1] < np.percentile(a[:, 1], 30)
    bottom = a[:, 1] > np.percentile(a[:, 1], 70)
    assert line_distance(a, b, size, bottom) > 2 * line_distance(a, b, size, top)


def test_similarity_inverse_round_trips():
    s = Similarity(1.3, 12.0, 40.0, -25.0)
    pts = np.array([[0.0, 0.0], [100.0, 50.0]])
    assert np.allclose(s.inverse().apply(s.apply(pts)), pts)
    assert math.isclose(s.inverse().scale, 1 / 1.3)
