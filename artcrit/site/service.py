"""Build the site and publish it in the background, one run at a time."""

import json
import logging
import threading
from pathlib import Path
from typing import Callable

from artcrit.config import Settings
from artcrit.site.export import export_site_images
from artcrit.site.lessons_page import lessons_html
from artcrit.site.model import build_site_data
from artcrit.site.publish import PublishResult, publish_site
from artcrit.site.render import render_site
from artcrit.store.images import ImageStore
from artcrit.store.sessions import SessionStore

log = logging.getLogger(__name__)


def build(store: SessionStore, images: ImageStore, settings: Settings) -> Path:
    data = build_site_data(store, settings.repo_dir)
    out = settings.site_dir
    mapping = export_site_images(data, images, out)
    render_site(data, mapping, lessons_html(settings.repo_dir, settings.lessons_dir), out)
    return out


def published_lessons_sha(settings: Settings) -> str | None:
    try:
        return json.loads(settings.publish_state.read_text()).get("lessons_sha")
    except (OSError, ValueError):
        return None


class Publisher:
    """Single-flight: at most one build+publish at a time; requests meanwhile collapse into one rerun."""

    def __init__(self, store: SessionStore, images: ImageStore, settings: Settings,
                 run_in_background: Callable[[Callable[[], None]], None],
                 build_fn: Callable = build, publish_fn: Callable = publish_site):
        self.store, self.images, self.settings = store, images, settings
        self.run_in_background, self.build_fn, self.publish_fn = run_in_background, build_fn, publish_fn
        self._lock = threading.Lock()
        self._running = self._pending = False
        self._last: PublishResult | None = None

    def request(self) -> None:
        with self._lock:
            if self._running:
                self._pending = True
                return
            self._running = True
        self.run_in_background(self._loop)

    def _loop(self) -> None:
        while True:
            self._once()
            with self._lock:
                if not self._pending:
                    self._running = False
                    return
                self._pending = False

    def _once(self) -> None:
        try:
            from artcrit.lessons import lessons_sha

            site = self.build_fn(self.store, self.images, self.settings)
            self._last = self.publish_fn(site, self.settings.repo_dir, self.settings.publish_state,
                                         extra_state={"lessons_sha": lessons_sha(self.settings.repo_dir)})
        except Exception as e:  # publishing is best-effort; never take the app down
            log.exception("publish failed")
            self._last = PublishResult(False, None, False, f"publish error: {e}")

    def last(self) -> PublishResult | None:
        if self._last is None:
            try:
                state = json.loads(self.settings.publish_state.read_text())
                self._last = PublishResult(state["committed"], state["commit"], state["pushed"], state["message"],
                                           state.get("at", ""))
            except (OSError, ValueError, KeyError):
                return None
        return self._last
