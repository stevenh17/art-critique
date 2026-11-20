import numpy as np

from artcrit.geometry.service import Geometry

from .test_landmarks import synthetic_face
from .test_outline import ellipse_drawing


def photo_like(h=500, w=400):
    img = np.full((h, w, 3), 225, np.uint8)
    import cv2

    cv2.ellipse(img, (w // 2, h // 2), (120, 170), 0, 0, 360, (90, 110, 150), -1)
    return img


def test_compare_available_on_light_drawing():
    c = Geometry(None).compare(ellipse_drawing(), photo_like())
    assert c.available and c.reason == ""
    assert 0 <= c.overall < 0.2
    assert c.sim is not None


def test_compare_unavailable_on_dark_drawing_with_reason():
    c = Geometry(None).compare(ellipse_drawing(bg=110), photo_like())
    assert not c.available and "too dark" in c.reason


def test_compare_unavailable_when_no_outline():
    c = Geometry(None).compare(np.full((300, 300, 3), 245, np.uint8), photo_like())
    assert not c.available and "outline" in c.reason


def test_region_distance_none_for_empty_region():
    c = Geometry(None).compare(ellipse_drawing(), photo_like())
    assert c.region_distance((0.0, 0.0, 0.05, 0.05)) is None
    assert c.region_distance((0.0, 0.5, 1.0, 1.0)) is not None


def test_full_matrix_maps_photo_into_drawing_pixels():
    drawing, photo = ellipse_drawing(), photo_like()
    c = Geometry(None).compare(drawing, photo)
    m = c.full_matrix()
    centre = m @ np.array([photo.shape[1] / 2, photo.shape[0] / 2, 1.0])
    assert abs(centre[0] - drawing.shape[1] / 2) < 25 and abs(centre[1] - drawing.shape[0] / 2) < 25


def test_faces_available_when_detector_finds_sane_faces():
    g = Geometry(None, detector=lambda img, model: synthetic_face())
    f = g.faces(ellipse_drawing(), photo_like())
    assert f.available and set(f.error) >= {"eye_line", "mouth"}


def test_faces_unavailable_when_detector_misses():
    f = Geometry(None, detector=lambda img, model: None).faces(ellipse_drawing(), photo_like())
    assert not f.available and "no face" in f.reason


def test_cached_once():
    calls = []

    def det(img, model):
        calls.append(1)
        return synthetic_face()

    g, d, p = Geometry(None, detector=det), ellipse_drawing(), photo_like()
    g.faces(d, p)
    g.faces(d, p)
    assert len(calls) == 2  # drawing + photo, once each
