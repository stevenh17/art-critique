import numpy as np
import pytest

from artcrit.imaging.regions import GRID_N, cells_to_box, crop, grid_overlay, to_png_b64, zoom


def test_grid_is_8():
    assert GRID_N == 8


def test_single_cell_a1():
    assert cells_to_box(["A1"]) == (0.0, 0.0, 0.125, 0.125)


def test_union_a1_b2():
    assert cells_to_box(["A1", "B2"]) == (0.0, 0.0, 0.25, 0.25)


def test_h8_is_bottom_right():
    assert cells_to_box(["H8"]) == (0.875, 0.875, 1.0, 1.0)


def test_lowercase_cell_accepted():
    assert cells_to_box(["c3"]) == (0.25, 0.25, 0.375, 0.375)


@pytest.mark.parametrize("bad", [["J9"], ["A0"], [""], ["A9"], [], ["AA1"]])
def test_invalid_cells_raise(bad):
    with pytest.raises(ValueError):
        cells_to_box(bad)


def test_crop_uses_normalized_box():
    img = np.zeros((100, 200, 3), np.uint8)
    assert crop(img, (0.5, 0.5, 1.0, 1.0)).shape == (50, 100, 3)


def test_zoom_caps_long_side():
    img = np.zeros((3000, 4000, 3), np.uint8)
    assert max(zoom(img, (0.0, 0.0, 1.0, 1.0)).shape[:2]) <= 1024


def test_zoom_padding_clamped_at_edges():
    img = np.zeros((100, 100, 3), np.uint8)
    out = zoom(img, (0.0, 0.0, 0.5, 0.5), max_side=10_000, pad=0.1)
    assert out.shape[:2] == (60, 60)  # padded only on the inner sides


def test_grid_overlay_keeps_shape():
    img = np.full((240, 320, 3), 255, np.uint8)
    out = grid_overlay(img)
    assert out.shape == img.shape
    assert (out != img).any()


def test_to_png_b64_is_png():
    import base64

    raw = base64.b64decode(to_png_b64(np.zeros((4, 4, 3), np.uint8)))
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
