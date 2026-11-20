import subprocess

from artcrit.cli import build_parser
from artcrit.config import Settings
from artcrit.site.publish import PublishResult
from artcrit.site.service import Publisher, build

from .test_publish import git


def settings_for(world, repo):
    return Settings(data_dir=world.tmp / "data", lessons_dir=repo / "lessons", repo_dir=repo, publish_enabled=True)


def make_repo(tmp_path):
    r = tmp_path / "repo"
    (r / "lessons" / "topics").mkdir(parents=True)
    (r / "lessons" / "core.md").write_text("# Core\n\nMeasure.\n")
    git(r.parent, "init", "-q", "-b", "main", str(r))
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    return r


def test_single_flight_collapses_requests(world, tmp_path):
    queued, runs = [], []
    p = Publisher(world.store, world.images, settings_for(world, tmp_path), queued.append,
                  build_fn=lambda *a: runs.append(1), publish_fn=lambda *a, **k: PublishResult(False, None, False, "x"))
    for _ in range(5):
        p.request()
    assert len(queued) == 1
    queued[0]()
    assert len(runs) == 2  # the first run, plus one collapsed follow-up


def test_publish_failure_never_raises(world, tmp_path):
    def boom(*a):
        raise RuntimeError("disk full")

    p = Publisher(world.store, world.images, settings_for(world, tmp_path), lambda fn: fn(), build_fn=boom)
    p.request()
    assert not p.last().pushed and "disk full" in p.last().message


def test_build_writes_site(world, tmp_path):
    repo = make_repo(tmp_path)
    d, _ = world.drawing()
    out = build(world.store, world.images, settings_for(world, repo))
    assert (out / f"drawings/d{d}.html").exists() and (out / "lessons.html").exists()


def test_unpublish_removes_from_branch(world, tmp_path):
    repo = make_repo(tmp_path)
    d, _ = world.drawing()
    p = Publisher(world.store, world.images, settings_for(world, repo), lambda fn: fn())
    p.request()
    files = git(repo, "ls-tree", "-r", "--name-only", "gh-pages").splitlines()
    assert f"drawings/d{d}.html" in files
    world.store.add_event("publish_toggle", payload={"publish": False, "drawing_id": d})
    p.request()
    files = git(repo, "ls-tree", "-r", "--name-only", "gh-pages").splitlines()
    assert f"drawings/d{d}.html" not in files and not any(f.startswith("assets/") for f in files)
    assert p.last().committed and "no remote" in p.last().message


def test_cli_publish_parses():
    assert build_parser().parse_args(["publish"]).command == "publish"


def test_settings_env_disables_publishing(monkeypatch):
    monkeypatch.setenv("ARTCRIT_PUBLISH", "0")
    assert Settings().publish_enabled is False
