import json

from artcrit.cli import build_parser
from artcrit.config import Settings
from artcrit.dreamer.git_pr import commit_branch
from artcrit.dreamer.run import run_dream
from artcrit.engine.base import AgentResult
from artcrit.engine.fake import FakeEngine
from artcrit.store.sessions import SessionStore
from tests.site.conftest import World, outcome

from .helpers import CORE, git, lesson_repo


def setup(tmp_path, evidence=True):
    repo = lesson_repo(tmp_path)
    world = World(tmp_path)
    sids = []
    for _ in range(2):
        d, pair = world.drawing(versions=2)
        sids += pair
        if evidence:
            issues = world.store.get_submission(pair[0]).issues
            outcome(world.store, issues[0].id, pair[1], "fixed")
            outcome(world.store, issues[1].id, pair[1], "not_fixed", "judge")
    settings = Settings(data_dir=tmp_path / "data", lessons_dir=repo / "lessons", repo_dir=repo, publish_enabled=False)
    return repo, world.store, settings, sids


def lesson_for(sids):
    cites = ", ".join(f"s{s}" for s in sids)
    return CORE + f"\n## Shorten the jaw from the mouth down\n- Measure chin to mouth in both images.\n- Evidence: {len(sids)} sessions. [{cites}]\n- Added 2026-11-21\n"


def agent(content=None):
    def run(tools):
        t = {x.name: x for x in tools}
        if content:
            t["write_lesson"].handler({"name": "core", "content": content})
        t["finish"].handler({"summary": "Proposed one lesson.", "changes": [] if not content else
                             [{"lesson": "core", "action": "add", "reason": "fixed", "sessions": ["s1"]}]})
        return AgentResult("ok", [], "fake")
    return run


def test_nothing_to_learn_makes_no_agent_call(tmp_path):
    repo, store, settings, _ = setup(tmp_path, evidence=False)
    eng = FakeEngine([])
    assert run_dream(store, settings, eng, today="2026-11-21").status == "nothing_to_learn"
    assert eng.calls == []


def test_pending_branch_refuses_unless_forced(tmp_path):
    repo, store, settings, sids = setup(tmp_path)
    commit_branch(repo, "main", {"lessons/core.md": "x\n"}, "dreamer/old", "old")
    rep = run_dream(store, settings, FakeEngine([]), today="2026-11-21")
    assert rep.status == "pending_branch" and "dreamer/old" in rep.detail
    forced = run_dream(store, settings, FakeEngine([agent()]), force=True, today="2026-11-21", push=False)
    assert forced.status == "no_change"


def test_happy_path_creates_branch_with_watermark(tmp_path):
    repo, store, settings, sids = setup(tmp_path)
    rep = run_dream(store, settings, FakeEngine([agent(lesson_for(sids))]), today="2026-11-21", push=False)
    assert rep.status == "branch_created" and rep.branch.startswith("dreamer/2026-11-21-")
    state = json.loads(git(repo, "show", f"{rep.branch}:lessons/.dreamer-state.json"))
    assert state["submission"] == max(sids) and state["outcome"] >= 4
    assert "Shorten the jaw" in git(repo, "show", f"{rep.branch}:lessons/core.md")
    assert git(repo, "status", "--porcelain") == "" and git(repo, "branch", "--show-current") == "main"
    assert (settings.data_dir / "dreamer" / "last-run.md").exists()


def test_checks_failed_no_branch_and_report_written(tmp_path):
    repo, store, settings, sids = setup(tmp_path)
    bad = agent(CORE + "\n## Made up\n- x\n- Evidence: [s9999]\n- Added 2026-11-21\n")
    rep = run_dream(store, settings, FakeEngine([bad, bad]), today="2026-11-21", push=False)
    assert rep.status == "checks_failed" and rep.branch is None
    assert git(repo, "for-each-ref", "refs/heads/dreamer/") == ""
    assert "s9999" in (settings.data_dir / "dreamer" / "last-run.md").read_text()


def test_dry_run_prints_diff_and_creates_nothing(tmp_path, capsys):
    repo, store, settings, sids = setup(tmp_path)
    rep = run_dream(store, settings, FakeEngine([agent(lesson_for(sids))]), today="2026-11-21", dry_run=True)
    assert rep.status == "dry_run" and rep.branch is None
    assert "+## Shorten the jaw" in rep.detail and git(repo, "for-each-ref", "refs/heads/dreamer/") == ""


def test_no_change_when_agent_edits_nothing(tmp_path):
    repo, store, settings, _ = setup(tmp_path)
    assert run_dream(store, settings, FakeEngine([agent()]), today="2026-11-21", push=False).status == "no_change"


def test_watermark_from_main_skips_processed_evidence(tmp_path):
    repo, store, settings, sids = setup(tmp_path)
    rep = run_dream(store, settings, FakeEngine([agent(lesson_for(sids))]), today="2026-11-21", push=False)
    git(repo, "merge", "-q", "--ff-only", rep.branch)  # Steven merges the PR
    again = run_dream(store, settings, FakeEngine([]), today="2026-11-22", push=False)
    assert again.status == "nothing_to_learn"


def test_cli_dream_parses():
    a = build_parser().parse_args(["dream", "--force", "--dry-run", "--no-push"])
    assert (a.command, a.force, a.dry_run, a.no_push) == ("dream", True, True, True)
