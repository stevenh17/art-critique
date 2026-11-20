"""Regression tests for the Plan 4 whole-branch review (I-1..I-4)."""

import pytest

from artcrit.dreamer.checks import run_checks
from artcrit.dreamer.export import EvidenceRecord, Export, Watermark, export_since
from artcrit.dreamer.git_pr import commit_branch, open_dreamer_branches
from artcrit.dreamer.workspace import LessonWorkspace, name_to_path
from artcrit.lessons import load_topic
from tests.site.conftest import World

from .helpers import CORE, HANDS, git, lesson_repo
from .test_run import agent, lesson_for, setup

FULL_CORE = CORE + """
## Say where and which way
- Point to cells on both images and give a direction.
- Evidence: seed lesson, no sessions yet.
- Added 2026-11-20
"""


def rec(n):
    return EvidenceRecord(f"s{n}", 1, "proportion", "t", "i", [], {"thumb_up": 1}, False, [])


EXPORT = Export([rec(10), rec(11), rec(12)], Watermark(12, 0, 0), [])
BASE = LessonWorkspace({"lessons/core.md": FULL_CORE, "lessons/topics/hands.md": HANDS})


def rules(new, changes=None):
    return {(f.path, f.rule) for f in run_checks(new, BASE, EXPORT, [], changes)}


# I-1: removing, hollowing or rewriting lessons needs this run's evidence
def test_hollowed_core_fails():
    hollow = LessonWorkspace({**BASE.files, "lessons/core.md": "# Core rubric\n\nChecks every critique uses.\n"})
    assert ("lessons/core.md", "core_minimum") in rules(hollow)
    assert ("lessons/core.md", "removal_needs_evidence") in rules(hollow)


def test_dropping_a_section_without_declared_retire_fails():
    dropped = LessonWorkspace({**BASE.files, "lessons/topics/hands.md": HANDS.split("## Hand size")[0]})
    assert ("lessons/topics/hands.md", "removal_needs_evidence") in rules(dropped)


def test_declared_retire_with_evidence_passes():
    dropped = LessonWorkspace({**BASE.files, "lessons/topics/hands.md": HANDS.split("## Hand size")[0] + "\n## Keep\n- x\n- Evidence: 3. [s10, s11, s12]\n- Added 2026-11-21\n"})
    changes = [{"lesson": "topics/hands: Hand size against the face", "action": "retire", "reason": "not fixed 3/3",
                "sessions": ["s10", "s11"]}]
    assert not any(r == "removal_needs_evidence" for _, r in rules(dropped, changes))


def test_rewriting_non_seed_lesson_needs_new_evidence():
    edited = HANDS.replace("A hand is about a face long.", "Hands are always tiny.")
    assert ("lessons/topics/hands.md", "change_needs_evidence") in rules(LessonWorkspace({**BASE.files, "lessons/topics/hands.md": edited}))
    cited = edited.replace("[s1, s2, s3, s4]", "[s1, s2, s3, s4, s10]")
    assert not any(r == "change_needs_evidence" for _, r in rules(LessonWorkspace({**BASE.files, "lessons/topics/hands.md": cited})))


# I-2: names with trailing newlines are rejected everywhere
@pytest.mark.parametrize("bad", ["topics/abc\n", "core\n", "topics/abc\n\n"])
def test_trailing_newline_names_rejected(bad):
    with pytest.raises(ValueError):
        name_to_path(bad)


def test_commit_branch_refuses_odd_paths(tmp_path):
    r = lesson_repo(tmp_path)
    with pytest.raises(ValueError):
        commit_branch(r, "main", {"lessons/topics/abc\n.md": "x\n"}, "dreamer/x", "m")
    with pytest.raises(ValueError):
        commit_branch(r, "main", {"artcrit/evil.py": "x\n"}, "dreamer/y", "m")


def test_critic_lesson_loader_rejects_newline_names(tmp_path):
    (tmp_path / "topics").mkdir()
    (tmp_path / "topics" / "abc.md").write_text("# A\n\nx\n")
    with pytest.raises(KeyError):
        load_topic(tmp_path, "abc\n")


# I-3: rows written during an export are neither lost nor counted early
def test_export_bounded_by_ids_read_first(tmp_path, monkeypatch):
    world = World(tmp_path)
    d, (s1,) = world.drawing()
    first = export_since(world.store, Watermark())
    iid = world.store.get_submission(s1).issues[0].id
    frozen = world.store.max_ids()
    world.store.add_event("thumb_down", issue_id=iid)  # written "during" the next export
    monkeypatch.setattr(world.store, "max_ids", lambda: frozen)
    during = export_since(world.store, first.new_watermark)
    assert during.records == [] and during.new_watermark == first.new_watermark
    monkeypatch.undo()
    after = export_since(world.store, first.new_watermark)
    assert len(after.records) == 1 and after.records[0].ratings["thumb_down"] == 1


# I-4: freshness of main and pending detection
def test_squash_merged_branch_is_not_pending(tmp_path):
    r = lesson_repo(tmp_path)
    state = '{"submission": 5, "outcome": 2, "event": 1}\n'
    commit_branch(r, "main", {"lessons/core.md": CORE + "\nx\n", "lessons/.dreamer-state.json": state}, "dreamer/a", "m")
    (r / "lessons" / ".dreamer-state.json").write_text(state)  # GitHub "squash and merge" result on main
    (r / "lessons" / "core.md").write_text(CORE + "\nx\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "Dreamer (#1)")
    assert open_dreamer_branches(r, "main") == []


def test_remote_only_dreamer_branch_is_pending(tmp_path):
    r = lesson_repo(tmp_path)
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(r, "remote", "add", "origin", str(bare))
    git(r, "push", "-q", "origin", "main")
    commit_branch(r, "main", {"lessons/core.md": "y\n", "lessons/.dreamer-state.json": '{"submission": 9, "outcome": 0, "event": 0}\n'},
                  "dreamer/b", "m")
    git(r, "push", "-q", "origin", "dreamer/b")
    git(r, "branch", "-D", "dreamer/b")
    git(r, "fetch", "-q", "origin")
    assert open_dreamer_branches(r, "main") == ["origin/dreamer/b"]


def test_run_bases_on_origin_main_when_local_is_behind(tmp_path):
    from artcrit.dreamer.run import run_dream
    from artcrit.engine.fake import FakeEngine

    repo, store, settings, sids = setup(tmp_path)
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "main")
    rep = run_dream(store, settings, FakeEngine([agent(lesson_for(sids))]), today="2026-11-21")
    assert rep.status == "branch_created"
    # The PR is merged on GitHub; Steven hasn't pulled, and the local branch is gone.
    git(bare, "update-ref", "refs/heads/main", git(repo, "rev-parse", rep.branch))
    git(repo, "branch", "-D", rep.branch)
    git(repo, "push", "-q", "origin", f":{rep.branch}")
    again = run_dream(store, settings, FakeEngine([]), today="2026-11-22")
    assert again.status == "nothing_to_learn", again.detail
