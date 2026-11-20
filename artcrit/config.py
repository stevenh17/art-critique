"""Paths the app reads and writes."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data")
    lessons_dir: Path = Path("lessons")
    repo_dir: Path = Path(".")

    @property
    def db_path(self) -> Path:
        return Path(self.data_dir) / "sessions.db"

    @property
    def images_dir(self) -> Path:
        return Path(self.data_dir) / "images"

    @property
    def uploads_dir(self) -> Path:
        return Path(self.data_dir) / "uploads"
