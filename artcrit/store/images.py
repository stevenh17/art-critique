"""Content-addressed PNG storage under data/."""

import hashlib
from pathlib import Path

import cv2
import numpy as np


class ImageStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def save(self, img: np.ndarray, kind: str) -> str:
        ok, buf = cv2.imencode(".png", img)
        if not ok:
            raise ValueError("PNG encoding failed")
        data = buf.tobytes()
        rel = f"{kind}/{hashlib.sha256(data).hexdigest()[:20]}.png"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        return rel

    def resolve(self, rel: str) -> Path:
        """Absolute path of a stored image; FileNotFoundError if missing or outside the root."""
        root = self.root.resolve()
        path = (root / rel).resolve()
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError(rel)
        return path

    def load(self, rel: str) -> np.ndarray:
        img = cv2.imread(str(self.resolve(rel)), cv2.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError(rel)
        return img
