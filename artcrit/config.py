"""Paths the app reads and writes, and the publishing switch."""

import os
from dataclasses import dataclass, field
from pathlib import Path


def _publish_default() -> bool:
    return os.environ.get("ARTCRIT_PUBLISH", "1") != "0"


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data")
    lessons_dir: Path = Path("lessons")
    repo_dir: Path = Path(".")
    publish_enabled: bool = field(default_factory=_publish_default)

    @property
    def db_path(self) -> Path:
        return Path(self.data_dir) / "sessions.db"

    @property
    def images_dir(self) -> Path:
        return Path(self.data_dir) / "images"

    @property
    def uploads_dir(self) -> Path:
        return Path(self.data_dir) / "uploads"

    @property
    def site_dir(self) -> Path:
        return Path(self.repo_dir) / "site"

    @property
    def publish_state(self) -> Path:
        return Path(self.data_dir) / "site-publish.json"
