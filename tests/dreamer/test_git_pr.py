import pytest

from artcrit.dreamer.agent import DreamResult
from artcrit.dreamer.export import Export, Watermark
from artcrit.dreamer.git_pr import (
    commit_branch,
    github_slug,
    open_dreamer_branches,
    open_pr,
    pr_body,
    push_branch,
)
from artcrit.dreamer.workspace import LessonWorkspace
from artcrit.site.publish import GitError

from .helpers import CORE, git, lesson_repo


def test_commit_branch_changes_only_given_files(tmp_path):
    r = lesson_repo(tmp_path)
    sha = commit_branch(r, "main", {"lessons/core.md": CORE + "\nmore\n", "lessons/.dreamer-state.json": "{}\n"},
                        "dreamer/a", "Dreamer: test")
    assert git(r, "rev-parse", "dreamer/a") == sha and git(r, "rev-parse", "dreamer/a^") == git(r, "rev-parse", "main")
    changed = git(r, "diff", "--name-only", "main", "dreamer/a").splitlines()
    assert sorted(changed) == ["lessons/.dreamer-state.json", "lessons/core.md"]
    assert git(r, "show", "dreamer/a:README.md") == "x"


def test_commit_branch_can_delete(tmp_path):
    r = lesson_repo(tmp_path)
    commit_branch(r, "main", {"lessons/topics/hands.md": None}, "dreamer/d", "rm")
    assert "lessons/topics/hands.md" not in git(r, "ls-tree", "-r", "--name-only", "dreamer/d")


def test_commit_branch_refuses_existing_branch(tmp_path):
    r = lesson_repo(tmp_path)
    commit_branch(r, "main", {"lessons/core.md": "a\n"}, "dreamer/a", "one")
    with pytest.raises(GitError):
        commit_branch(r, "main", {"lessons/core.md": "b\n"}, "dreamer/a", "two")


def test_checkout_untouched(tmp_path):
    r = lesson_repo(tmp_path)
    git(r, "checkout", "-q", "-b", "feature")
    (r / "lessons" / "core.md").write_text("uncommitted edit\n")
    (r / "staged.txt").write_text("s")
    git(r, "add", "staged.txt")
    before = (git(r, "status", "--porcelain"), git(r, "rev-parse", "HEAD"), git(r, "branch", "--show-current"))
    commit_branch(r, "main", {"lessons/core.md": CORE + "\nx\n"}, "dreamer/b", "msg")
    after = (git(r, "status", "--porcelain"), git(r, "rev-parse", "HEAD"), git(r, "branch", "--show-current"))
    assert before == after


def test_push_branch_to_bare_remote(tmp_path):
    r = lesson_repo(tmp_path)
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(r, "remote", "add", "origin", str(bare))
    commit_branch(r, "main", {"lessons/core.md": "a\n"}, "dreamer/p", "m")
    ok, msg = push_branch(r, "dreamer/p")
    assert ok, msg
    assert git(bare, "rev-parse", "dreamer/p") == git(r, "rev-parse", "dreamer/p")


def test_push_branch_without_remote(tmp_path):
    r = lesson_repo(tmp_path)
    commit_branch(r, "main", {"lessons/core.md": "a\n"}, "dreamer/p", "m")
    assert push_branch(r, "dreamer/p") == (False, "no remote 'origin'")


@pytest.mark.parametrize("url,slug", [
    ("https://github.com/stevenh17/art-critique.git", "stevenh17/art-critique"),
    ("https://github.com/o/r", "o/r"),
    ("git@github.com:o/r.git", "o/r"),
    ("https://gitlab.com/o/r.git", None),
])
def test_github_slug_variants(url, slug):
    assert github_slug(url) == slug


def test_open_pr_falls_back_to_compare_url_without_gh(tmp_path, monkeypatch):
    r = lesson_repo(tmp_path)
    git(r, "remote", "add", "origin", "https://github.com/o/r.git")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # no gh
    assert open_pr(r, "dreamer/x", "T", "B") == ("compare", "https://github.com/o/r/compare/main...dreamer/x?expand=1")


def test_open_pr_without_github_remote(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert open_pr(lesson_repo(tmp_path), "dreamer/x", "T", "B")[0] == "none"


def test_pr_body_has_test_gate_line_and_attribution():
    res = DreamResult(True, LessonWorkspace({}), "Strengthened the eye-line lesson.",
                      [{"lesson": "core", "action": "strengthen", "reason": "fixed 4/5", "sessions": ["s10", "s11"]}])
    body = pr_body(res, Export([], Watermark(12, 3, 9), []), " lessons/core.md | 3 ++-")
    assert "Not checked by a test gate (TODO)" in body
    assert body.rstrip().endswith("🤖 Generated with [Claude Code](https://claude.com/claude-code)")
    assert "| core | strengthen | fixed 4/5 | s10, s11 |" in body and "s12" in body


def test_open_dreamer_branches_lists_unmerged_only(tmp_path):
    r = lesson_repo(tmp_path)
    commit_branch(r, "main", {"lessons/core.md": "a\n"}, "dreamer/open", "m")
    git(r, "branch", "dreamer/merged", "main")
    assert open_dreamer_branches(r) == ["dreamer/open"]
