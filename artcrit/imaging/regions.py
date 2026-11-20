"""Grid cells, normalized boxes, crops and zooms shared by the critic and the UI."""

import base64
import re

import cv2
import numpy as np

Box = tuple[float, float, float, float]  # normalized (x0, y0, x1, y1) in [0, 1]

GRID_N = 8
COLS = "ABCDEFGH"
_CELL = re.compile(r"^([A-H])([1-8])$")


def cells_to_box(cells: list[str]) -> Box:
    """Union of grid cells (columns A-H left→right, rows 1-8 top→bottom) as a normalized box."""
    if not cells:
        raise ValueError("at least one grid cell is required")
    xs, ys = [], []
    for cell in cells:
        m = _CELL.match(str(cell).strip().upper())
        if not m:
            raise ValueError(f"invalid grid cell {cell!r}; use A1-H8")
        xs.append(COLS.index(m.group(1)))
        ys.append(int(m.group(2)) - 1)
    return (min(xs) / GRID_N, min(ys) / GRID_N, (max(xs) + 1) / GRID_N, (max(ys) + 1) / GRID_N)


def _px(img: np.ndarray, box: Box) -> tuple[int, int, int, int]:
    h, w = img.shape[:2]
    x0, y0, x1, y1 = (min(max(v, 0.0), 1.0) for v in box)
    return round(x0 * w), round(y0 * h), max(round(x1 * w), round(x0 * w) + 1), max(round(y1 * h), round(y0 * h) + 1)


def crop(img: np.ndarray, box: Box) -> np.ndarray:
    x0, y0, x1, y1 = _px(img, box)
    return img[y0:y1, x0:x1]


def zoom(img: np.ndarray, box: Box, max_side: int = 1024, pad: float = 0.05) -> np.ndarray:
    """Crop `box` plus `pad` (fraction of the image) on each side, clamped, downscaled to max_side."""
    x0, y0, x1, y1 = box
    out = crop(img, (x0 - pad, y0 - pad, x1 + pad, y1 + pad))
    h, w = out.shape[:2]
    scale = max_side / max(h, w)
    if scale < 1:
        out = cv2.resize(out, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    return out


def grid_overlay(img: np.ndarray) -> np.ndarray:
    """Copy of `img` with an 8×8 grid and A1…H8 labels drawn on it."""
    out = img.copy()
    h, w = out.shape[:2]
    color, thick = (40, 40, 220), max(1, round(min(h, w) / 400))
    for i in range(1, GRID_N):
        x, y = round(i * w / GRID_N), round(i * h / GRID_N)
        cv2.line(out, (x, 0), (x, h - 1), color, thick)
        cv2.line(out, (0, y), (w - 1, y), color, thick)
    font_scale = max(0.3, min(h, w) / 1200)
    for c in range(GRID_N):
        for r in range(GRID_N):
            org = (round(c * w / GRID_N) + 3, round(r * h / GRID_N) + round(14 * font_scale / 0.5))
            cv2.putText(out, f"{COLS[c]}{r + 1}", org, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thick, cv2.LINE_AA)
    return out


def to_png_b64(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("PNG encoding failed")
    return base64.b64encode(buf.tobytes()).decode()
