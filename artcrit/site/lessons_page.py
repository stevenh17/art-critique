"""Lessons rendered for the public site, each with its git change history."""

import html
import subprocess
from dataclasses import dataclass
from pathlib import Path

import markdown


@dataclass
class LessonHistory:
    date: str
    sha: str
    subject: str


def lesson_history(repo_dir: Path, rel_path: str, limit: int = 20) -> list[LessonHistory]:
    try:
        out = subprocess.run(
            ["git", "log", "--follow", f"-n{limit}", "--format=%ad%x09%h%x09%s", "--date=short", "--", rel_path],
            cwd=repo_dir, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    rows = [line.split("\t", 2) for line in out.stdout.splitlines() if line.count("\t") >= 2]
    return [LessonHistory(*r) for r in rows]


def _section(repo_dir: Path, lessons_dir: Path, path: Path) -> str:
    body = markdown.markdown(html.escape(path.read_text(), quote=False), extensions=["extra"])
    try:
        rel = path.resolve().relative_to(Path(repo_dir).resolve()).as_posix()
    except ValueError:  # lessons outside the repo: no history
        rel = path.name
    hist = lesson_history(repo_dir, rel)
    items = "".join(f"<li>{html.escape(h.date)} · <code>{html.escape(h.sha)}</code> · {html.escape(h.subject)}</li>"
                    for h in hist)
    history = f'<details class="history"><summary>History</summary><ul>{items}</ul></details>' if hist else ""
    return f'<section class="lesson">{body}{history}</section>'


def lessons_html(repo_dir: Path, lessons_dir: Path) -> str:
    lessons_dir = Path(lessons_dir)
    paths = [lessons_dir / "core.md", *sorted((lessons_dir / "topics").glob("*.md"))]
    return "\n".join(_section(repo_dir, lessons_dir, p) for p in paths if p.is_file())
