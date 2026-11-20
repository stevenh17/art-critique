"""Decode uploaded image bytes into upright BGR arrays."""

import io

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # pragma: no cover - HEIC support is optional at runtime
    pass


class UnsupportedImageError(ValueError):
    """The uploaded bytes are not an image format we can read."""


def load_image(data: bytes) -> np.ndarray:
    """Return a BGR uint8 array, rotated per EXIF orientation. Supports HEIC."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        rgb = np.asarray(img.convert("RGB"))
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise UnsupportedImageError(f"Unsupported or corrupt image: {e}") from e
    return np.ascontiguousarray(rgb[:, :, ::-1])
