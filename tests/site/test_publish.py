import json
import subprocess

import pytest

from artcrit.site.publish import commit_site, publish_site, push_site


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    (r / "README.md").write_text("hi\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    site = r / "site"
    site.mkdir()
    (site / "index.html").write_text("<h1>v1</h1>")
    (site / "assets").mkdir()
    (site / "assets" / "a.jpg").write_bytes(b"\xff\xd8\xffjpeg")
    return r, site


def tree_files(repo, ref="gh-pages"):
    return sorted(git(repo, "ls-tree", "-r", "--name-only", ref).splitlines())


def test_first_publish_creates_branch_with_site_files(repo):
    r, site = repo
    sha = commit_site(site, r)
    assert sha and git(r, "rev-parse", "gh-pages") == sha
    assert tree_files(r) == ["assets/a.jpg", "index.html"]


def test_second_publish_without_changes_makes_no_commit(repo):
    r, site = repo
    commit_site(site, r)
    assert commit_site(site, r) is None


def test_changed_site_makes_child_commit(repo):
    r, site = repo
    first = commit_site(site, r)
    (site / "assets" / "a.jpg").unlink()
    (site / "index.html").write_text("<h1>v2</h1>")
    second = commit_site(site, r)
    assert git(r, "rev-parse", f"{second}^") == first
    assert tree_files(r) == ["index.html"]


def test_working_tree_index_and_head_untouched(repo):
    r, site = repo
    git(r, "checkout", "-q", "-b", "feature")
    (r / "README.md").write_text("uncommitted edit\n")
    (r / "staged.txt").write_text("x")
    git(r, "add", "staged.txt")
    before = (git(r, "status", "--porcelain"), git(r, "rev-parse", "HEAD"), git(r, "branch", "--show-current"))
    commit_site(site, r)
    after = (git(r, "status", "--porcelain"), git(r, "rev-parse", "HEAD"), git(r, "branch", "--show-current"))
    assert before == after


def test_no_remote_reports_not_pushed(repo, tmp_path):
    r, site = repo
    res = publish_site(site, r, tmp_path / "state.json")
    assert res.committed and not res.pushed and "no remote" in res.message


def test_push_to_bare_remote(repo, tmp_path):
    r, site = repo
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(r, "remote", "add", "origin", str(bare))
    res = publish_site(site, r, tmp_path / "state.json")
    assert res.pushed
    assert git(bare, "rev-parse", "gh-pages") == git(r, "rev-parse", "gh-pages")


def test_failed_push_retried_next_time(repo, tmp_path):
    r, site = repo
    git(r, "remote", "add", "origin", str(tmp_path / "missing.git"))
    state = tmp_path / "state.json"
    first = publish_site(site, r, state)
    assert first.committed and not first.pushed
    bare = tmp_path / "missing.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    second = publish_site(site, r, state)
    assert not second.committed and second.pushed
    assert json.loads(state.read_text())["pushed"] is True


def test_push_site_never_forces(repo, tmp_path, monkeypatch):
    import artcrit.site.publish as pub

    seen = []
    real = pub._git
    monkeypatch.setattr(pub, "_git", lambda *a, **k: seen.append(a) or real(*a, **k))
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    r, site = repo
    git(r, "remote", "add", "origin", str(bare))
    commit_site(site, r)
    push_site(r)
    pushes = [a for a in seen if "push" in a]
    assert pushes and not any("--force" in a or "-f" in a or any(str(x).startswith("+") for x in a) for a in pushes)
