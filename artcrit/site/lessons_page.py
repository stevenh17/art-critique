"""Lessons rendered for the public site, each with its git change history.

The site shows lessons as merged on `main` (or HEAD when there is no main), never the
working tree, so unreviewed edits and dreamer PR branches stay private."""

import html
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import markdown


@dataclass
class LessonHistory:
    date: str
    sha: str
    subject: str


def _git(repo_dir: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=repo_dir, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None


def site_lessons_ref(repo_dir: Path) -> str | None:
    """The ref whose lessons are public: main if it exists, else HEAD; None outside a git repo."""
    for ref in ("refs/heads/main", "HEAD"):
        if _git(repo_dir, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") is not None:
            return ref
    return None


def lesson_history(repo_dir: Path, rel_path: str, limit: int = 20, ref: str = "HEAD") -> list[LessonHistory]:
    out = _git(repo_dir, "log", ref, "--follow", f"-n{limit}", "--format=%ad%x09%h%x09%s", "--date=short",
               "--", rel_path)
    if not out:
        return []
    return [LessonHistory(*line.split("\t", 2)) for line in out.splitlines() if line.count("\t") >= 2]


_TAG_IMG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_HREF = re.compile(r'\s(href|src)="([^"]*)"', re.IGNORECASE)


def _safe_links(rendered: str) -> str:
    """Drop images and any link whose scheme isn't http(s) (relative links and #anchors are kept)."""
    rendered = _TAG_IMG.sub("", rendered)

    def fix(m: re.Match) -> str:
        value = re.sub(r"[\x00-\x20]", "", html.unescape(m.group(2)))
        return m.group(0) if urlparse(value).scheme in ("", "http", "https") else ""

    return _HREF.sub(fix, rendered)


def _render(text: str) -> str:
    return _safe_links(markdown.markdown(html.escape(text, quote=False), extensions=["extra"]))


def _history_html(hist: list[LessonHistory]) -> str:
    if not hist:
        return ""
    items = "".join(f"<li>{html.escape(h.date)} · <code>{html.escape(h.sha)}</code> · {html.escape(h.subject)}</li>"
                    for h in hist)
    return f'<details class="history"><summary>History</summary><ul>{items}</ul></details>'


def _from_git(repo_dir: Path, ref: str, rel_dir: str) -> list[tuple[str, str]]:
    names = (_git(repo_dir, "ls-tree", "-r", "--name-only", ref, "--", rel_dir) or "").splitlines()
    core = f"{rel_dir}/core.md"
    topics = sorted(n for n in names if n.startswith(f"{rel_dir}/topics/") and n.endswith(".md"))
    paths = ([core] if core in names else []) + topics
    return [(p, _git(repo_dir, "show", f"{ref}:{p}") or "") for p in paths]


def lessons_html(repo_dir: Path, lessons_dir: Path) -> str:
    repo_dir, lessons_dir = Path(repo_dir), Path(lessons_dir)
    ref = site_lessons_ref(repo_dir)
    try:
        rel_dir = lessons_dir.resolve().relative_to(repo_dir.resolve()).as_posix()
    except ValueError:
        ref = None
    if ref is not None:
        sections = _from_git(repo_dir, ref, rel_dir)
        return "\n".join(f'<section class="lesson">{_render(text)}{_history_html(lesson_history(repo_dir, p, ref=ref))}</section>'
                         for p, text in sections)
    # Not a git repo: nothing is "merged", so show the files as they are (no history).
    paths = [lessons_dir / "core.md", *sorted((lessons_dir / "topics").glob("*.md"))]
    return "\n".join(f'<section class="lesson">{_render(p.read_text())}</section>' for p in paths if p.is_file())
