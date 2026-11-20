import io

import numpy as np
import pytest
from PIL import Image

from artcrit.imaging.load import UnsupportedImageError, load_image


def _encode(img: Image.Image, fmt: str, **kw) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt, **kw)
    return buf.getvalue()


def test_load_png_roundtrip():
    img = Image.new("RGB", (30, 20), (255, 0, 0))
    arr = load_image(_encode(img, "PNG"))
    assert arr.shape == (20, 30, 3)
    assert arr.dtype == np.uint8
    assert tuple(arr[0, 0]) == (0, 0, 255)  # BGR


def test_load_heic():
    pillow_heif = pytest.importorskip("pillow_heif")
    pillow_heif.register_heif_opener()
    img = Image.new("RGB", (64, 32), (0, 255, 0))
    try:
        data = _encode(img, "HEIF")
    except Exception:  # encoder unavailable on this platform
        pytest.skip("HEIF encoder unavailable")
    assert load_image(data).shape == (32, 64, 3)


def test_exif_orientation_6_is_rotated():
    img = Image.new("RGB", (200, 100), (10, 20, 30))
    exif = Image.Exif()
    exif[0x0112] = 6
    arr = load_image(_encode(img, "JPEG", exif=exif))
    assert arr.shape == (200, 100, 3)


def test_garbage_bytes_raises_unsupported():
    with pytest.raises(UnsupportedImageError):
        load_image(b"not an image at all")
