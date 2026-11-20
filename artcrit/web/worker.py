"""Runs one critique for a submission and records the outcome as status rows."""

import logging

from artcrit.config import Settings
from artcrit.critic import critique
from artcrit.critique_schema import CritiqueFormatError
from artcrit.engine.base import AgentEngine, EngineError, UsageLimitError
from artcrit.imaging.regions import crop
from artcrit.store.images import ImageStore
from artcrit.store.sessions import SessionStore

log = logging.getLogger(__name__)

FAILED_MESSAGE = "critique failed — retry"
LIMIT_MESSAGE = "usage limit reached — retry later"


def run_critique(submission_id: int, store: SessionStore, images: ImageStore, engine: AgentEngine,
                 settings: Settings) -> None:
    sub = store.get_submission(submission_id)
    store.add_status(submission_id, "running")
    try:
        drawing = images.load(sub.normalized_path)
        photo = crop(images.load(sub.photo_path), sub.photo_crop)
        run = critique(drawing, photo, settings.lessons_dir, engine,
                       intentional=store.intentional_boxes(sub.drawing_id), repo_dir=settings.repo_dir)
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
    store.add_critique(submission_id, run)
    store.add_status(submission_id, "done")
