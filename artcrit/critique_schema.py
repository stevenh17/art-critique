"""The critic's output contract: 2–3 located, directional issues in instructor order."""

import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from artcrit.imaging.regions import Box, cells_to_box

Category = Literal["proportion", "anatomy", "values", "edges"]
CATEGORY_ORDER: tuple[str, ...] = ("proportion", "anatomy", "values", "edges")


class CritiqueFormatError(ValueError):
    """The model's output didn't match the critique contract. The message is fed back on retry."""


class Issue(BaseModel):
    category: Category
    title: str = Field(max_length=80, min_length=1)
    instruction: str = Field(min_length=1)
    drawing_cells: list[str]
    photo_cells: list[str]
    lesson_refs: list[str] = []

    @field_validator("drawing_cells", "photo_cells")
    @classmethod
    def _valid_cells(cls, v: list[str]) -> list[str]:
        cells_to_box(v)  # raises ValueError on bad cells
        return [c.strip().upper() for c in v]

    @property
    def drawing_box(self) -> Box:
        return cells_to_box(self.drawing_cells)

    @property
    def photo_box(self) -> Box:
        return cells_to_box(self.photo_cells)


class Critique(BaseModel):
    issues: list[Issue] = Field(min_length=2, max_length=3)

    @field_validator("issues")
    @classmethod
    def _instructor_order(cls, v: list[Issue]) -> list[Issue]:
        return sorted(v, key=lambda i: CATEGORY_ORDER.index(i.category))


CRITIQUE_JSON_INSTRUCTIONS = """\
Finish with a single JSON object and nothing after it, in exactly this shape:
{"issues": [
  {"category": "proportion" | "anatomy" | "values" | "edges",
   "title": "<short name, max 80 chars>",
   "instruction": "<what to change, where, in which direction, and roughly how much>",
   "drawing_cells": ["<grid cells on the drawing, e.g. C6, D6>"],
   "photo_cells": ["<matching grid cells on the reference photo>"],
   "lesson_refs": ["<headings of lessons you used, may be empty>"]}
]}
Give 2 or 3 issues — never fewer than 2, never more than 3. Grid cells use columns A-H (left to right) and rows 1-8 (top to bottom)."""


def _json_objects(text: str) -> list[object]:
    """Top-level JSON objects found in free text, in order."""
    dec, found, i = json.JSONDecoder(), [], 0
    while (i := text.find("{", i)) != -1:
        try:
            obj, end = dec.raw_decode(text, i)
        except json.JSONDecodeError:
            i += 1
            continue
        found.append(obj)
        i = end
    return found


def parse_critique(text: str) -> Critique:
    objects = [o for o in _json_objects(text) if isinstance(o, dict)]
    if not objects:
        raise CritiqueFormatError("No JSON object found. " + CRITIQUE_JSON_INSTRUCTIONS)
    try:
        return Critique.model_validate(objects[-1])
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
        raise CritiqueFormatError(f"Invalid critique JSON ({problems}). {CRITIQUE_JSON_INSTRUCTIONS}") from e
