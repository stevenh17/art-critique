"""Web-sized, content-hashed JPEGs for the public site."""

import hashlib
from pathlib import Path

import cv2
import numpy as np

from artcrit.imaging.regions import crop, fit
from artcrit.site.model import SiteData
from artcrit.store.images import ImageStore

PUBLISH_MAX_SIDE = 1600
JPEG_QUALITY = 85


def export_image(img: np.ndarray, out_dir: Path) -> str:
    small = fit(img, PUBLISH_MAX_SIDE)
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise ValueError("JPEG encoding failed")
    rel = f"assets/{hashlib.blake2b(np.ascontiguousarray(small).data, digest_size=16).hexdigest()}.jpg"
    path = Path(out_dir) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(buf.tobytes())
    return rel


def export_site_images(data: SiteData, images: ImageStore, out_dir: Path) -> dict[str, str]:
    """Map every image ref in `data` to its exported path. Photos are cropped to the critic's frame."""
    mapping: dict[str, str] = {}
    for d in data.drawings:
        if d.photo_image not in mapping:
            mapping[d.photo_image] = export_image(crop(images.load(d.photo_image), d.photo_crop), out_dir)
        for v in d.versions:
            if v.drawing_image not in mapping:
                mapping[v.drawing_image] = export_image(images.load(v.drawing_image), out_dir)
    return mapping
