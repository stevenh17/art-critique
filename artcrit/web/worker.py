"""Runs one critique for a submission and records the outcome as status rows."""

import logging

from artcrit.config import Settings
from artcrit.critic import critique
from artcrit.critique_schema import CritiqueFormatError
from artcrit.engine.base import AgentEngine, EngineError, UsageLimitError
from artcrit.geometry.service import Geometry
from artcrit.outcomes import evaluate_revision
from artcrit.imaging.regions import crop
from artcrit.store.images import ImageStore
from artcrit.store.sessions import SessionStore

log = logging.getLogger(__name__)

FAILED_MESSAGE = "critique failed — retry"
LIMIT_MESSAGE = "usage limit reached — retry later"


def run_submission(submission_id: int, store: SessionStore, images: ImageStore, engine: AgentEngine,
                   settings: Settings, geometry: Geometry | None = None) -> None:
    """For a revision, first judge the previous version's issues; then critique this version fresh."""
    sub = store.get_submission(submission_id)
    store.add_status(submission_id, "running")
    try:
        revision = None
        if sub.parent_id is not None:
            revision = evaluate_revision(store.get_submission(sub.parent_id), sub, images, engine, geometry)
        drawing = images.load(sub.normalized_path)
        photo = crop(images.load(sub.photo_path), sub.photo_crop)
        run = critique(drawing, photo, settings.lessons_dir, engine,
                       intentional=store.intentional_boxes(sub.drawing_id), repo_dir=settings.repo_dir,
                       geometry=geometry)
    except UsageLimitError as e:
        store.add_status(submission_id, "limit", f"{LIMIT_MESSAGE} ({e})")
        return
    except EngineError as e:
        store.add_status(submission_id, "failed", f"{FAILED_MESSAGE} ({e})"[:500])
        return
    except CritiqueFormatError:
        store.add_status(submission_id, "failed", FAILED_MESSAGE)
        return
    except Exception as e:  # never leave a submission stuck in 'running'
        log.exception("critique %s crashed", submission_id)
        store.add_status(submission_id, "failed", f"{FAILED_MESSAGE} ({type(e).__name__})")
        return
    if revision is not None:  # stored only once everything succeeded, so a retry never shows duplicates
        for row in revision.outcomes:
            store.add_outcome(row)
        store.add_revision_metrics(submission_id, revision.overall_old, revision.overall_new)
    store.add_critique(submission_id, run)
    store.add_status(submission_id, "done")


run_critique = run_submission  # Plan 1 name
