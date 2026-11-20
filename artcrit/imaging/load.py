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
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            img = Image.alpha_composite(white, rgba)
        rgb = np.asarray(img.convert("RGB"))
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as e:
        raise UnsupportedImageError(f"Unsupported or corrupt image: {e}") from e
    return np.ascontiguousarray(rgb[:, :, ::-1])
