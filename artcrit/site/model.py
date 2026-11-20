"""Everything the public site shows, and nothing else. This module decides what is public."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from artcrit.imaging.regions import Box
from artcrit.lessons import lessons_sha
from artcrit.store.sessions import SessionStore


@dataclass
class SiteIssue:
    number: int
    category: str
    title: str
    instruction: str
    drawing_box: Box
    photo_box: Box
    intentional: bool
    ratings: dict[str, int]


@dataclass
class SiteOutcome:
    number: int
    title: str
    verdict: str
    measured: bool


@dataclass
class SiteVersion:
    version: int
    slug: str
    drawing_image: str  # ImageStore ref; mapped to a published asset at export time
    issues: list[SiteIssue]
    outcomes: list[SiteOutcome]
    closeness: float | None
    lessons_sha: str
    model: str


@dataclass
class SiteDrawing:
    id: int
    slug: str
    title: str
    photo_image: str
    photo_crop: Box
    source_url: str | None
    license: str
    versions: list[SiteVersion] = field(default_factory=list)


@dataclass
class SiteData:
    drawings: list[SiteDrawing]
    generated_at: str
    lessons_sha: str


def _safe_url(url: str) -> str | None:
    return url if urlparse(url).scheme in ("http", "https") else None


def _version(store: SessionStore, sid: int) -> SiteVersion | None:
    v = store.get_submission(sid)
    if v is None or v.status != "done":
        return None
    issues = [SiteIssue(i.number, i.category, i.title, i.instruction, i.drawing_box, i.photo_box, i.intentional,
                        store.rating_counts(i.id)) for i in v.issues]
    outcomes, closeness = [], None
    if v.parent_id is not None:
        outcomes = [SiteOutcome(o.number, o.title, o.final_verdict, o.source.startswith("geometry"))
                    for o in store.outcomes_for(v.id)]
        metrics = store.revision_metrics(v.id)
        if metrics and metrics[0] and metrics[1] is not None:
            closeness = 1 - metrics[1] / metrics[0]
    return SiteVersion(v.version, f"d{v.drawing_id}-v{v.version}", v.normalized_path, issues, outcomes, closeness,
                       v.lessons_sha or "", v.model or "")


def build_site_data(store: SessionStore, repo_dir: Path) -> SiteData:
    drawings = []
    for d in store.published_drawing_ids():
        versions = [sv for sid, _ in store.versions(d) if (sv := _version(store, sid)) is not None]
        if not versions:
            continue
        first = store.get_submission(store.versions(d)[0][0])
        drawings.append(SiteDrawing(d, f"d{d}", f"Drawing {d}", first.photo_path, first.photo_crop,
                                    _safe_url(first.photo_source_url), first.photo_license, versions))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    from artcrit.site.lessons_page import site_lessons_ref

    return SiteData(drawings, now, lessons_sha(repo_dir, site_lessons_ref(repo_dir) or "HEAD"))
