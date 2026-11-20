import cv2
import numpy as np

from artcrit.site.export import PUBLISH_MAX_SIDE, export_image, export_site_images
from artcrit.site.model import build_site_data


def test_export_downscales_and_is_jpeg(tmp_path):
    img = np.random.default_rng(0).integers(0, 255, (3000, 4000, 3), dtype=np.uint8)
    rel = export_image(img, tmp_path)
    assert rel.startswith("assets/") and rel.endswith(".jpg")
    raw = (tmp_path / rel).read_bytes()
    assert raw[:3] == b"\xff\xd8\xff"
    assert max(cv2.imread(str(tmp_path / rel)).shape[:2]) == PUBLISH_MAX_SIDE


def test_same_pixels_same_name(tmp_path):
    img = np.full((50, 60, 3), 90, np.uint8)
    assert export_image(img, tmp_path) == export_image(img.copy(), tmp_path)


def test_photo_exported_cropped_and_mapping_complete(world, tmp_path):
    world.drawing(versions=2)
    data = build_site_data(world.store, world.tmp)
    mapping = export_site_images(data, world.images, tmp_path / "out")
    d = data.drawings[0]
    assert set(mapping) == {d.photo_image, *(v.drawing_image for v in d.versions)}
    photo = cv2.imread(str(tmp_path / "out" / mapping[d.photo_image]))
    assert photo.shape[:2] == (320, 480)  # 400x600 cropped to the middle 80% on each axis
