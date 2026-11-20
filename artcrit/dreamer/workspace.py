"""An in-memory copy of the merged lessons, and the only tools the dreamer agent gets.

Nothing here writes to disk: the agent edits this copy, and changes reach the repo only
as a commit on a new branch (git_pr.py) that Steven reviews."""

import copy
import re
import subprocess
from pathlib import Path

from artcrit.engine.base import ToolSpec

LESSONS = "lessons"
STATE_PATH = f"{LESSONS}/.dreamer-state.json"
MAX_FILE_CHARS = 20_000
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


def name_to_path(name: str) -> str:
    if name == "core":
        return f"{LESSONS}/core.md"
    if isinstance(name, str) and name.startswith("topics/") and _SLUG.fullmatch(name[len("topics/"):]):
        return f"{LESSONS}/topics/{name[len('topics/'):]}.md"
    raise ValueError(f"invalid lesson name {name!r}; use 'core' or 'topics/<slug>' (lowercase letters, digits, dashes)")


def is_lesson_path(path: str) -> bool:
    return path == STATE_PATH or _path_to_name(path) is not None


def _path_to_name(path: str) -> str | None:
    if path == f"{LESSONS}/core.md":
        return "core"
    m = re.fullmatch(rf"{LESSONS}/topics/([a-z0-9][a-z0-9-]{{0,40}})\.md", path)
    return f"topics/{m.group(1)}" if m else None


def _git(repo_dir: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo_dir, capture_output=True, text=True, timeout=15)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return out.stdout


def description(text: str) -> str:
    for line in text.splitlines():
        if line.strip() and not line.startswith("#"):
            return line.strip()
    return ""


class LessonWorkspace:
    def __init__(self, files: dict[str, str]):
        self.files = dict(files)  # repo-relative path -> content

    @staticmethod
    def from_ref(repo_dir: Path, ref: str) -> "LessonWorkspace":
        paths = _git(repo_dir, "ls-tree", "-r", "--name-only", ref, "--", LESSONS).splitlines()
        return LessonWorkspace({p: _git(repo_dir, "show", f"{ref}:{p}") for p in paths})

    def copy(self) -> "LessonWorkspace":
        return LessonWorkspace(copy.deepcopy(self.files))

    def names(self) -> list[str]:
        names = [n for p in self.files if (n := _path_to_name(p))]
        return sorted(names, key=lambda n: (n != "core", n))

    def read(self, name: str) -> str:
        path = name_to_path(name)
        if path not in self.files:
            raise KeyError(name)
        return self.files[path]

    def write(self, name: str, content: str) -> None:
        path = name_to_path(name)
        if not isinstance(content, str) or len(content) > MAX_FILE_CHARS:
            raise ValueError(f"content must be text of at most {MAX_FILE_CHARS} characters")
        self.files[path] = content if content.endswith("\n") else content + "\n"

    def state(self) -> str | None:
        return self.files.get(STATE_PATH)

    def changed(self, base: "LessonWorkspace") -> dict[str, str | None]:
        out: dict[str, str | None] = {p: c for p, c in self.files.items() if base.files.get(p) != c}
        out.update({p: None for p in base.files if p not in self.files})
        return out


def _text(s: str) -> list[dict]:
    return [{"type": "text", "text": s}]


def make_tools(ws: LessonWorkspace, sink: dict) -> list[ToolSpec]:
    def list_lessons(args: dict):
        return _text("\n".join(f"{n}: {description(ws.read(n))}" for n in ws.names()) or "(no lessons)")

    def read_lesson(args: dict):
        try:
            return _text(ws.read(str(args.get("name", ""))))
        except (ValueError, KeyError) as e:
            return _text(f"Error: no such lesson ({e}). Use list_lessons.")

    def write_lesson(args: dict):
        try:
            ws.write(args.get("name", ""), args.get("content", ""))
        except ValueError as e:
            return _text(f"Error: {e}")
        return _text(f"Saved {args.get('name')}.")

    def finish(args: dict):
        sink["finish"] = {"summary": str(args.get("summary", "")), "changes": list(args.get("changes") or [])}
        return _text("Recorded. You are done.")

    name = {"type": "string", "description": "'core' or 'topics/<slug>'"}
    change = {"type": "object", "properties": {
        "lesson": {"type": "string"}, "action": {"type": "string", "enum": ["strengthen", "rewrite", "merge", "retire", "add"]},
        "reason": {"type": "string"}, "sessions": {"type": "array", "items": {"type": "string"}}},
        "required": ["lesson", "action", "reason", "sessions"]}
    return [
        ToolSpec("list_lessons", "List lesson files with their one-line descriptions.",
                 {"type": "object", "properties": {}}, list_lessons),
        ToolSpec("read_lesson", "Read one lesson file.", {"type": "object", "properties": {"name": name},
                 "required": ["name"]}, read_lesson),
        ToolSpec("write_lesson", "Replace one lesson file with new full markdown content (creates topics/<slug>).",
                 {"type": "object", "properties": {"name": name, "content": {"type": "string"}},
                  "required": ["name", "content"]}, write_lesson),
        ToolSpec("finish", "Call once at the end with a summary and every change you made (or none).",
                 {"type": "object", "properties": {"summary": {"type": "string"},
                  "changes": {"type": "array", "items": change}}, "required": ["summary", "changes"]}, finish),
    ]
