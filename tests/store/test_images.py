import numpy as np

from artcrit.store.images import ImageStore


def test_save_and_load_roundtrip(tmp_path):
    store = ImageStore(tmp_path)
    img = np.random.default_rng(0).integers(0, 255, (20, 30, 3), dtype=np.uint8)
    rel = store.save(img, "drawing")
    assert rel.startswith("drawing/") and rel.endswith(".png")
    assert (store.load(rel) == img).all()


def test_identical_images_share_a_path(tmp_path):
    store = ImageStore(tmp_path)
    img = np.zeros((5, 5, 3), np.uint8)
    assert store.save(img, "photo") == store.save(img.copy(), "photo")


def test_load_rejects_paths_outside_root(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        ImageStore(tmp_path / "root").load("../x.png")
