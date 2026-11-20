"""Read-only access to the curated lessons in lessons/ (written only by the dreamer)."""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class TopicInfo:
    name: str
    description: str


def load_core(lessons_dir: Path) -> str:
    return (Path(lessons_dir) / "core.md").read_text()


def _description(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return ""


def list_topics(lessons_dir: Path) -> list[TopicInfo]:
    files = sorted((Path(lessons_dir) / "topics").glob("*.md"))
    return [TopicInfo(f.stem, _description(f.read_text())) for f in files]


def load_topic(lessons_dir: Path, name: str) -> str:
    if not _NAME.match(name or ""):
        raise KeyError(name)
    path = Path(lessons_dir) / "topics" / f"{name}.md"
    if not path.is_file():
        raise KeyError(name)
    return path.read_text()


def lessons_sha(repo_dir: Path) -> str:
    """Git tree SHA of lessons/ at HEAD, or 'uncommitted' when unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD:lessons"], cwd=repo_dir, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return "uncommitted"
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else "uncommitted"
