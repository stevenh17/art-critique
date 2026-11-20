import numpy as np
import pytest

from artcrit.geometry.points import POINT_NAMES, measure_from_points, points_error

FACE = np.array([[100, 200], [220, 200], [160, 260], [160, 380], [160, 90], [160, 320]], float)  # px


def test_six_named_points():
    assert len(POINT_NAMES) == 6 and POINT_NAMES[3] == "chin"


def test_points_error_zero_for_similar_sets():
    photo = FACE * 1.7 + (40, -15)  # same face, bigger photo, shifted
    assert points_error(FACE, photo).max() < 1e-6


def test_points_error_flags_moved_chin():
    drawing = FACE.copy()
    drawing[3, 1] += 40  # chin a third of a head too low
    err = points_error(drawing, FACE * 2.0)
    assert err.argmax() == 3 and err[3] > 0.25


def test_measure_from_points_uses_points_in_box():
    old = FACE.copy()
    old[3, 1] += 40
    shape = (480, 320)
    chin_box = (0.3, 0.7, 0.7, 0.9)  # chin at y=420/480 ≈ 0.875 in the old drawing
    m = measure_from_points(chin_box, old, FACE.copy(), FACE * 1.5, shape)
    assert m.source == "points" and m.confident and m.old > 0.25 and m.new == pytest.approx(0, abs=1e-6)
