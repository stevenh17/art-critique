"""`artcrit dream`: one dreamer run from evidence to a reviewable branch."""

import difflib
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from artcrit.config import Settings
from artcrit.dreamer.agent import DreamResult, dream
from artcrit.dreamer.export import Export, Watermark, export_since, has_enough_evidence
from artcrit.dreamer.git_pr import base_ref, commit_branch, open_dreamer_branches, open_pr, pr_body, push_branch, refresh_remote
from artcrit.dreamer.workspace import STATE_PATH, LessonWorkspace
from artcrit.engine.base import AgentEngine
from artcrit.store.sessions import SessionStore

Status = Literal["nothing_to_learn", "pending_branch", "no_change", "checks_failed", "dry_run", "branch_created"]


@dataclass
class RunReport:
    status: Status
    detail: str
    branch: str | None = None
    link: tuple[str, str] | None = None


def _diff(base: LessonWorkspace, files: dict[str, str | None]) -> str:
    out = []
    for path, new in sorted(files.items()):
        old = base.files.get(path, "")
        out += difflib.unified_diff(old.splitlines(keepends=True), (new or "").splitlines(keepends=True),
                                    f"a/{path}", f"b/{path}")
    return "".join(out)


def _write_report(settings: Settings, rep: RunReport, result: DreamResult | None, export: Export | None) -> None:
    path = settings.data_dir / "dreamer" / "last-run.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Dreamer run {datetime.now().isoformat(timespec='seconds')}", "", f"Status: **{rep.status}**", "",
             rep.detail]
    if export is not None:
        lines += ["", f"Evidence records: {len(export.records)}"]
    if result is not None:
        lines += ["", "## Summary", "", result.summary]
        if result.failures:
            lines += ["", "## Failed checks", ""] + [f"- {f.path} [{f.rule}]: {f.detail}" for f in result.failures]
    path.write_text("\n".join(lines) + "\n")


def run_dream(store: SessionStore, settings: Settings, engine: AgentEngine, *, force: bool = False,
              dry_run: bool = False, today: str | None = None, push: bool = True) -> RunReport:
    repo = settings.repo_dir
    now = datetime.now()
    today = today or now.date().isoformat()
    export: Export | None = None
    result: DreamResult | None = None

    def finish(rep: RunReport) -> RunReport:
        _write_report(settings, rep, result, export)
        return rep

    refresh_remote(repo)
    base_rev = base_ref(repo)
    pending = open_dreamer_branches(repo, base_rev)
    if pending and not force:
        return finish(RunReport("pending_branch", "Unmerged dreamer branch(es): " + ", ".join(pending)
                                + ". Merge or delete them first (or pass --force)."))
    base = LessonWorkspace.from_ref(repo, base_rev)
    export = export_since(store, Watermark.load(base.state()))
    if not force and not has_enough_evidence(export):
        return finish(RunReport("nothing_to_learn", f"Only {len(export.records)} new issue records, too few with "
                                "outcomes or ratings to learn from yet."))
    result = dream(export, base, engine, store.user_texts(), today)
    if not result.ok:
        return finish(RunReport("checks_failed", "The proposal did not pass the safety checks; nothing was created."))
    files = {p: c for p, c in result.workspace.changed(base).items() if p != STATE_PATH}
    if not files:
        return finish(RunReport("no_change", "The dreamer proposed no lesson changes for this evidence."))
    files[STATE_PATH] = export.new_watermark.dumps()
    if dry_run:
        return finish(RunReport("dry_run", _diff(base, files)))
    branch = f"dreamer/{today}-{now:%H%M}"
    title = f"Dreamer: {result.summary.splitlines()[0][:72] if result.summary else 'lesson updates'}"
    commit_branch(repo, base_rev, files, branch, title)
    stat = subprocess.run(["git", "diff", "--stat", base_rev, branch], cwd=repo, capture_output=True, text=True).stdout
    link = None
    detail = f"Created branch {branch}."
    if push:
        ok, msg = push_branch(repo, branch)
        detail += f" {msg}."
        if ok:
            link = open_pr(repo, branch, title, pr_body(result, export, stat.strip()))
    return finish(RunReport("branch_created", detail, branch, link))
