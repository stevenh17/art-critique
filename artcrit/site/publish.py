"""Commit the built site onto the gh-pages branch and push it, without touching the checkout.

Uses a temporary index and `--work-tree=site/`, so the working tree, real index, HEAD and the
checked-out branch are never modified. Never force-pushes."""

import json
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

_NO_PROMPT = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
FALLBACK_IDENTITY = ("-c", "user.name=artcrit", "-c", "user.email=artcrit@localhost")


@dataclass
class PublishResult:
    committed: bool
    commit: str | None
    pushed: bool
    message: str
    at: str = ""


class GitError(RuntimeError):
    pass


def _git(repo_dir: Path, *args: str, env: dict | None = None, timeout: int = 60) -> str:
    out = subprocess.run(["git", *args], cwd=repo_dir, capture_output=True, text=True, env=env, timeout=timeout)
    if out.returncode != 0:
        raise GitError((out.stderr or out.stdout).strip()[-500:])
    return out.stdout.strip()


def _identity(repo_dir: Path) -> tuple[str, ...]:
    try:
        _git(repo_dir, "config", "user.email")
        return ()
    except GitError:
        return FALLBACK_IDENTITY


def _ref(repo_dir: Path, ref: str) -> str | None:
    try:
        return _git(repo_dir, "rev-parse", "--verify", "--quiet", ref)
    except GitError:
        return None


def _parent(repo_dir: Path, branch: str, remote: str = "origin") -> str | None:
    """Local branch tip, or the remote's when the local branch is missing or behind (e.g. a fresh clone)."""
    local = _ref(repo_dir, f"refs/heads/{branch}")
    try:
        _git(repo_dir, "remote", "get-url", remote)
        _git(repo_dir, "fetch", "--quiet", remote, f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}",
             env=_NO_PROMPT, timeout=30)
    except (GitError, subprocess.TimeoutExpired):
        return local
    upstream = _ref(repo_dir, f"refs/remotes/{remote}/{branch}")
    if upstream is None or local == upstream:
        return local
    if local is None:
        return upstream
    try:
        _git(repo_dir, "merge-base", "--is-ancestor", local, upstream)
        return upstream  # local is behind: build on the remote so the push fast-forwards
    except GitError:
        return local


def commit_site(site_dir: Path, repo_dir: Path, branch: str = "gh-pages") -> str | None:
    """New commit on `branch` holding exactly the files in site_dir; None if nothing changed."""
    site_dir, repo_dir = Path(site_dir).resolve(), Path(repo_dir).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        _git(repo_dir, f"--work-tree={site_dir}", "add", "-A", "-f", ".", env=env)
        tree = _git(repo_dir, "write-tree", env=env)
    local = _ref(repo_dir, f"refs/heads/{branch}")
    parent = _parent(repo_dir, branch)
    if parent and _git(repo_dir, "rev-parse", f"{parent}^{{tree}}") == tree:
        if parent != local:  # nothing new, but catch the local branch up to the remote
            _git(repo_dir, "update-ref", f"refs/heads/{branch}", parent, local or "0" * 40)
        return None
    args = ["commit-tree", tree, "-m", "Publish site"] + (["-p", parent] if parent else [])
    commit = _git(repo_dir, *_identity(repo_dir), *args)
    _git(repo_dir, "update-ref", f"refs/heads/{branch}", commit, *([local] if local else ["0" * 40]))
    return commit


def push_site(repo_dir: Path, branch: str = "gh-pages", remote: str = "origin") -> tuple[bool, str]:
    try:
        _git(repo_dir, "remote", "get-url", remote)
    except GitError:
        return False, f"no remote '{remote}'"
    try:
        _git(repo_dir, "push", "--quiet", remote, f"refs/heads/{branch}:refs/heads/{branch}")
    except (GitError, subprocess.TimeoutExpired) as e:
        return False, f"push failed: {e}"
    return True, f"pushed to {remote}/{branch}"


def _load(state_path: Path) -> dict:
    try:
        return json.loads(Path(state_path).read_text())
    except (OSError, ValueError):
        return {}


def publish_site(site_dir: Path, repo_dir: Path, state_path: Path, extra_state: dict | None = None) -> PublishResult:
    """Commit, then push when there is a new commit or the last push didn't succeed."""
    previous = _load(state_path)
    commit = commit_site(site_dir, repo_dir)
    pushed, message = False, "no changes"
    if commit is not None or not previous.get("pushed", False):
        pushed, message = push_site(repo_dir)
    elif previous.get("pushed"):
        pushed, message = True, "no changes; already pushed"
    result = PublishResult(commit is not None, commit or _ref(repo_dir, "refs/heads/gh-pages"), pushed, message,
                           datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    Path(state_path).parent.mkdir(parents=True, exist_ok=True)
    Path(state_path).write_text(json.dumps({**asdict(result), **(extra_state or {})}))
    return result
