"""Put a dreamer proposal on its own branch and open a PR, without touching the checkout.

Same approach as the site publisher: a temporary index built from the base ref, so the
working tree, the real index, HEAD and the checked-out branch never change. Never force-pushes."""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from artcrit.dreamer.agent import DreamResult
from artcrit.dreamer.export import Export, Watermark
from artcrit.dreamer.workspace import STATE_PATH, is_lesson_path
from artcrit.site.publish import _NO_PROMPT, GitError, _identity

ZERO = "0" * 40
TEST_GATE_LINE = "Not checked by a test gate (TODO)"
ATTRIBUTION = "🤖 Generated with [Claude Code](https://claude.com/claude-code)"


def _git(repo_dir: Path, *args: str, env: dict | None = None, input: str | None = None, timeout: int = 60) -> str:
    out = subprocess.run(["git", *args], cwd=repo_dir, capture_output=True, text=True, env=env, input=input,
                         timeout=timeout)
    if out.returncode != 0:
        raise GitError((out.stderr or out.stdout).strip()[:500])
    return out.stdout.strip()


def commit_branch(repo_dir: Path, base_ref: str, files: dict[str, str | None], branch: str, message: str) -> str:
    bad = [p for p in files if not is_lesson_path(p)]
    if bad:
        raise ValueError(f"refusing to commit non-lesson paths: {bad!r}")
    base = _git(repo_dir, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        _git(repo_dir, "read-tree", base, env=env)
        for path, content in sorted(files.items()):
            if content is None:
                _git(repo_dir, "update-index", "--force-remove", "--", path, env=env)
            else:
                blob = _git(repo_dir, "hash-object", "-w", "--stdin", input=content)
                _git(repo_dir, "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env)
        tree = _git(repo_dir, "write-tree", env=env)
    commit = _git(repo_dir, *_identity(repo_dir), "commit-tree", tree, "-p", base, "-m", message)
    _git(repo_dir, "update-ref", f"refs/heads/{branch}", commit, ZERO)  # fails if the branch already exists
    return commit


def push_branch(repo_dir: Path, branch: str, remote: str = "origin") -> tuple[bool, str]:
    try:
        _git(repo_dir, "remote", "get-url", remote)
    except GitError:
        return False, f"no remote '{remote}'"
    try:
        _git(repo_dir, "push", "--quiet", remote, f"refs/heads/{branch}:refs/heads/{branch}", env=_NO_PROMPT)
    except (GitError, subprocess.TimeoutExpired) as e:
        return False, f"push failed: {e}"
    return True, f"pushed {branch}"


def github_slug(remote_url: str) -> str | None:
    m = re.match(r"^(?:https://github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?/?$", remote_url.strip())
    return m.group(1) if m else None


def open_pr(repo_dir: Path, branch: str, title: str, body: str) -> tuple[str, str]:
    if shutil.which("gh"):
        out = subprocess.run(["gh", "pr", "create", "--base", "main", "--head", branch, "--title", title,
                              "--body-file", "-"], cwd=repo_dir, input=body, capture_output=True, text=True,
                             timeout=60)
        if out.returncode == 0 and out.stdout.strip():
            return "pr", out.stdout.strip().splitlines()[-1]
    try:
        slug = github_slug(_git(repo_dir, "remote", "get-url", "origin"))
    except GitError:
        slug = None
    if slug is None:
        return "none", "no GitHub remote"
    return "compare", f"https://github.com/{slug}/compare/main...{branch}?expand=1"


def pr_body(result: DreamResult, export: Export, diffstat: str) -> str:
    rows = "\n".join(f"| {c.get('lesson', '')} | {c.get('action', '')} | {c.get('reason', '')} | "
                     f"{', '.join(c.get('sessions', []))} |" for c in result.changes) or "| — | — | no changes listed | |"
    wm = export.new_watermark
    sessions = sorted({r.session for r in export.records}, key=lambda s: int(s[1:]))
    return f"""## Summary

{result.summary}

## Changes

| Lesson | Action | Reason | Evidence |
|---|---|---|---|
{rows}

## Evidence

{len(export.records)} issue records from sessions {', '.join(sessions) or '—'} (watermark: submission s{wm.submission}, outcome {wm.outcome}, event {wm.event}). Merging this PR marks that evidence as processed.

## Checks

All deterministic gates passed (format, core size, evidence exists, new-lesson support, no user text, no links or images).
{TEST_GATE_LINE}

```
{diffstat}
```

Proposed by the dreamer agent ({result.model}). Review the wording and evidence before merging; revert the merge commit to roll back.

{ATTRIBUTION}
"""


def _state(repo_dir: Path, ref: str) -> Watermark:
    try:
        return Watermark.load(_git(repo_dir, "show", f"{ref}:{STATE_PATH}"))
    except GitError:
        return Watermark()


def _covered(branch: Watermark, base: Watermark) -> bool:
    return (branch.submission, branch.outcome, branch.event) != (0, 0, 0) and \
        branch.submission <= base.submission and branch.outcome <= base.outcome and branch.event <= base.event


def refresh_remote(repo_dir: Path, remote: str = "origin") -> None:
    """Best-effort fetch of main and dreamer branches (pruning deleted ones). Never raises."""
    try:
        _git(repo_dir, "remote", "get-url", remote)
        _git(repo_dir, "fetch", "--quiet", "--prune", remote, f"+refs/heads/main:refs/remotes/{remote}/main",
             f"+refs/heads/dreamer/*:refs/remotes/{remote}/dreamer/*", env=_NO_PROMPT, timeout=30)
    except (GitError, subprocess.TimeoutExpired):
        pass


def base_ref(repo_dir: Path, remote: str = "origin") -> str:
    """origin/main when local main is behind it (e.g. a merged PR not pulled yet), else main."""
    try:
        local = _git(repo_dir, "rev-parse", "--verify", "refs/heads/main")
        upstream = _git(repo_dir, "rev-parse", "--verify", f"refs/remotes/{remote}/main")
    except GitError:
        return "main"
    if local != upstream:
        try:
            _git(repo_dir, "merge-base", "--is-ancestor", local, upstream)
            return f"refs/remotes/{remote}/main"
        except GitError:
            pass
    return "main"


def open_dreamer_branches(repo_dir: Path, base: str = "main") -> list[str]:
    """Dreamer branches (local, or on origin) whose evidence `base` hasn't absorbed yet.

    A branch counts as merged if it is an ancestor of base (merge commit) or base's watermark already
    covers the branch's watermark (squash or rebase merge)."""
    local = _git(repo_dir, "for-each-ref", "--format=%(refname:short)", "refs/heads/dreamer/").splitlines()
    remote = [r for r in _git(repo_dir, "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/dreamer/").splitlines()
              if r.removeprefix("origin/") not in local]
    base_state = _state(repo_dir, base)
    open_ = []
    for b in local + remote:
        try:
            _git(repo_dir, "merge-base", "--is-ancestor", b, base)
            continue
        except GitError:
            pass
        if not _covered(_state(repo_dir, b), base_state):
            open_.append(b)
    return sorted(open_)
