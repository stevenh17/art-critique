"""Did each flagged issue get fixed? The judge decides, unless confident measurement says otherwise.

Geometry overrides the judge only for proportion issues; every disagreement is logged."""

import json
from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np

from artcrit.engine.base import AgentEngine
from artcrit.geometry.landmarks import RATIO_FEATURES
from artcrit.geometry.service import Geometry, map_box
from artcrit.imaging.regions import Box, crop, zoom
from artcrit.judge import JudgeResult, Verdict, judge_issue
from artcrit.store.images import ImageStore
from artcrit.store.sessions import OutcomeRow, SubmissionView

__all__ = ["OutcomeRow", "GeometryMeasure", "RevisionResult", "evaluate_revision", "final_verdict", "measure_issue",
           "ratio_verdict", "geo_verdict"]

# Starting thresholds (spec §8 leaves them to the builder; revisit once the test set exists).
FIXED_RATIO = 0.6
PARTLY_RATIO = 0.85
NOISE_FLOOR = 0.015  # region error at or below this (fraction of subject/face size) isn't measurable
LANDMARK_FIXED = 0.5
LANDMARK_PARTLY = 0.8
MAX_LANDMARK_FEATURES = 2  # more features in the box means the issue isn't about specific features


@dataclass
class GeometryMeasure:
    source: Literal["outline", "landmarks", "points"]
    old: float
    new: float
    confident: bool


@dataclass
class RevisionResult:
    outcomes: list[OutcomeRow]
    overall_old: float | None
    overall_new: float | None


def ratio_verdict(old: float, new: float, fixed: float, partly: float) -> Verdict:
    if new <= fixed * old:
        return "fixed"
    if new <= partly * old:
        return "partly"
    return "not_fixed"


def geo_verdict(m: GeometryMeasure) -> Verdict:
    if m.source == "outline":
        return ratio_verdict(m.old, m.new, FIXED_RATIO, PARTLY_RATIO)
    return ratio_verdict(m.old, m.new, LANDMARK_FIXED, LANDMARK_PARTLY)


def _in_box(pt: np.ndarray, box: Box) -> bool:
    return box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3]


def measure_issue(issue_box: Box, old, new, old_faces, new_faces, new_box: Box | None = None) -> GeometryMeasure | None:
    """Landmarks when the issue is about one or two specific facial features and both versions have
    confident faces; otherwise outline distance in the region (e.g. whole-head shape issues)."""
    keys = []
    if old_faces.available and new_faces.available:
        keys = [k for k, names in RATIO_FEATURES.items()
                if _in_box(np.mean([old_faces.drawing.p(n) for n in names], axis=0), issue_box)]
    if 0 < len(keys) <= MAX_LANDMARK_FEATURES:
        o = float(np.mean([old_faces.error[k] for k in keys]))
        n = float(np.mean([new_faces.error[k] for k in keys]))
        return GeometryMeasure("landmarks", o, n, o > NOISE_FLOOR)
    if not (old.available and new.available):
        return None
    o, n = old.region_distance(issue_box), new.region_distance(new_box or issue_box)
    if o is None or n is None:
        return None
    # Too little measured change in the region to call it either way: leave it to the judge.
    return GeometryMeasure("outline", o, n, o > NOISE_FLOOR and abs(o - n) > NOISE_FLOOR)


def final_verdict(category: str, judge: JudgeResult, geo: GeometryMeasure | None) -> tuple[Verdict, str, bool]:
    if geo is None or not geo.confident:
        return judge.verdict, "judge", False
    measured = geo_verdict(geo)
    disagreement = measured != judge.verdict
    if category == "proportion":
        return measured, f"geometry:{geo.source}", disagreement
    return judge.verdict, "judge", disagreement


def evaluate_revision(prev: SubmissionView, new: SubmissionView, images: ImageStore, engine: AgentEngine,
                      geometry: Geometry | None) -> RevisionResult:
    issues = [i for i in prev.issues if not i.intentional]
    if not issues:
        return RevisionResult([], None, None)
    old_d, new_d = images.load(prev.normalized_path), images.load(new.normalized_path)
    photo = crop(images.load(prev.photo_path), prev.photo_crop)
    comps = faces = None
    if geometry is not None:
        comps = (geometry.compare(old_d, photo), geometry.compare(new_d, photo))
        faces = (geometry.faces(old_d, photo), geometry.faces(new_d, photo))
    rows = []
    for issue in issues:
        new_box = map_box(issue.drawing_box, *comps) if comps else issue.drawing_box
        judged = judge_issue(issue.category, issue.title, issue.instruction, zoom(old_d, issue.drawing_box),
                             zoom(new_d, new_box), zoom(photo, issue.photo_box), engine)
        geo = measure_issue(issue.drawing_box, *comps, *faces, new_box=new_box) if comps else None
        verdict, source, disagree = final_verdict(issue.category, judged, geo)
        rows.append(OutcomeRow(issue.id, new.id, judged.verdict, judged.reason,
                               json.dumps(asdict(geo) if geo else {"unavailable": True}), verdict, source, disagree))
    overall_old = comps[0].overall if comps and comps[0].available else None
    overall_new = comps[1].overall if comps and comps[1].available else None
    return RevisionResult(rows, overall_old, overall_new)
