"""Regression tests for the Plan 2 whole-branch review (I-1..I-5)."""

import numpy as np
import pytest

from artcrit.geometry.outline import Similarity
from artcrit.geometry.points import POINTS_NOISE, measure_from_points
from artcrit.geometry.service import CACHE_SIZE, Comparison, Geometry, map_box
from artcrit.outcomes import measure_issue

from .geometry.test_outline import ellipse_drawing
from .geometry.test_points import FACE
from .geometry.test_service import photo_like
from .test_outcomes import StubComp, StubFaces


# I-1: content-keyed, bounded cache that holds no images
def test_cache_hits_on_equal_content_and_holds_no_arrays():
    calls = []

    def det(img, model):
        calls.append(1)
        return None

    g = Geometry(None, detector=det)
    d, p = ellipse_drawing(), photo_like()
    g.faces(d, p)
    g.faces(d.copy(), p.copy())  # same pixels, new arrays (as every caller loads fresh)
    assert len(calls) == 2
    g.compare(d, p)
    g.compare(d.copy(), p.copy())
    held = [v for cache in (g._outline, g._faces, g._detected) for v in cache.values()]
    assert not any(isinstance(x, np.ndarray) for v in held for x in (v if isinstance(v, tuple) else (v,)))


def test_cache_is_bounded():
    g = Geometry(None, detector=lambda i, m: None)
    for k in range(CACHE_SIZE + 5):
        img = np.full((40, 40, 3), k, np.uint8)
        g.faces(img, img)
    assert len(g._detected) <= CACHE_SIZE and len(g._faces) <= CACHE_SIZE


# I-2: unchanged silhouette never overrides the judge
def test_unchanged_outline_region_is_not_confident():
    m = measure_issue((0, 0, 1, 1), StubComp(region=0.05), StubComp(region=0.045), StubFaces(), StubFaces())
    assert m is not None and not m.confident


# I-4: issue box mapped through the photo onto the new drawing
def _comp(sim, shape=(600, 400)):
    return Comparison(True, "", sim, None, None, 1.0, shape, 1.0, 1.0, 0.0)


def test_map_box_follows_shifted_subject():
    old = _comp(Similarity(1.0, 0.0, 0.0, 0.0))
    new = _comp(Similarity(1.0, 0.0, 40.0, 60.0))  # subject drawn 40px right, 60px lower on the new sheet
    x0, y0, x1, y1 = map_box((0.25, 0.25, 0.5, 0.5), old, new)
    assert (x0, y0, x1, y1) == pytest.approx((0.35, 0.35, 0.6, 0.6))


def test_map_box_identity_when_unavailable():
    assert map_box((0.1, 0.2, 0.3, 0.4), Comparison(False), _comp(Similarity(1, 0, 0, 0))) == (0.1, 0.2, 0.3, 0.4)


def test_measure_issue_uses_mapped_box_for_new_version():
    class Rec(StubComp):
        def region_distance(self, box):
            self.box = box
            return self.region

    old, new = Rec(region=0.1), Rec(region=0.03)
    measure_issue((0, 0, 0.5, 0.5), old, new, StubFaces(), StubFaces(), new_box=(0.1, 0.1, 0.6, 0.6))
    assert old.box == (0, 0, 0.5, 0.5) and new.box == (0.1, 0.1, 0.6, 0.6)


# I-5: click imprecision is not "measured"
def test_points_below_noise_not_confident():
    old = FACE.copy()
    old[3, 1] += 0.02 * 120  # chin off by 2% of eye distance: within click noise
    m = measure_from_points((0, 0, 1, 1), old, FACE.copy(), FACE * 1.5, (480, 320))
    assert POINTS_NOISE > 0 and not m.confident
