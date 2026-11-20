"""Append-only SQLite session log: one record per submission plus event rows."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Literal, get_args

from artcrit.critic import CritiqueRun
from artcrit.imaging.regions import Box, cells_to_box

EventType = Literal["thumb_up", "thumb_down", "unclear", "intentional", "show_me", "help_measure", "publish_toggle"]
Status = Literal["queued", "running", "done", "failed", "limit"]
RATINGS = ("thumb_up", "thumb_down", "unclear")


@dataclass
class IssueView:
    id: int
    number: int
    category: str
    title: str
    instruction: str
    drawing_cells: list[str]
    photo_cells: list[str]
    rating: str | None
    intentional: bool

    @property
    def drawing_box(self) -> Box:
        return cells_to_box(self.drawing_cells)

    @property
    def photo_box(self) -> Box:
        return cells_to_box(self.photo_cells)


@dataclass
class OutcomeRow:
    issue_id: int
    revision_submission_id: int
    judge_verdict: str
    judge_reason: str
    geometry_json: str
    final_verdict: str
    source: str
    disagreement: bool


@dataclass
class OutcomeView:
    issue_id: int
    number: int
    category: str
    title: str
    final_verdict: str
    source: str
    judge_verdict: str
    judge_reason: str
    disagreement: bool


@dataclass
class SubmissionView:
    id: int
    drawing_id: int
    version: int
    normalized_path: str
    photo_path: str
    photo_crop: Box
    photo_source_url: str
    photo_license: str
    publish: bool
    status: str
    status_detail: str
    model: str | None
    lessons_sha: str | None
    issues: list[IssueView]
    parent_id: int | None = None


class SessionStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(files("artcrit.store").joinpath("schema.sql").read_text())

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # commits on success, rolls back on error
                yield conn
        finally:
            conn.close()

    def _insert(self, sql: str, params: tuple) -> int:
        with self._conn() as c:
            return c.execute(sql, params).lastrowid

    def add_drawing(self, photo_path: str, photo_crop: Box, photo_source_url: str, photo_license: str, publish: bool) -> int:
        return self._insert(
            "INSERT INTO drawings (photo_path, photo_crop, photo_source_url, photo_license, publish) VALUES (?,?,?,?,?)",
            (photo_path, json.dumps(list(photo_crop)), photo_source_url, photo_license, int(publish)),
        )

    def add_submission(self, drawing_id: int, version: int, parent_id: int | None, original_path: str,
                       normalized_path: str, corners) -> int:
        sid = self._insert(
            "INSERT INTO submissions (drawing_id, version, parent_id, original_path, normalized_path, corners) "
            "VALUES (?,?,?,?,?,?)",
            (drawing_id, version, parent_id, original_path, normalized_path, json.dumps([list(p) for p in corners])),
        )
        self.add_status(sid, "queued")
        return sid

    def add_status(self, submission_id: int, status: Status, detail: str = "") -> None:
        if status not in get_args(Status):
            raise ValueError(f"unknown status {status!r}")
        self._insert("INSERT INTO submission_status (submission_id, status, detail) VALUES (?,?,?)",
                     (submission_id, status, detail))

    def add_critique(self, submission_id: int, run: CritiqueRun) -> list[int]:
        with self._conn() as c:
            cid = c.execute(
                "INSERT INTO critiques (submission_id, critique_json, tool_trace, model, lessons_sha) VALUES (?,?,?,?,?)",
                (submission_id, run.critique.model_dump_json(), json.dumps(run.tool_trace), run.model, run.lessons_sha),
            ).lastrowid
            return [
                c.execute(
                    "INSERT INTO issues (critique_id, submission_id, position, category, title, instruction, "
                    "drawing_cells, photo_cells, lesson_refs) VALUES (?,?,?,?,?,?,?,?,?)",
                    (cid, submission_id, n, i.category, i.title, i.instruction, json.dumps(i.drawing_cells),
                     json.dumps(i.photo_cells), json.dumps(i.lesson_refs)),
                ).lastrowid
                for n, i in enumerate(run.critique.issues, start=1)
            ]

    def add_event(self, type: EventType, issue_id: int | None = None, submission_id: int | None = None,
                  payload: dict | None = None) -> int:
        if type not in get_args(EventType):
            raise ValueError(f"unknown event type {type!r}")
        return self._insert("INSERT INTO events (type, issue_id, submission_id, payload) VALUES (?,?,?,?)",
                            (type, issue_id, submission_id, json.dumps(payload or {})))

    def get_issue(self, issue_id: int) -> sqlite3.Row | None:
        with self._conn() as c:
            return c.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()

    def _issue_views(self, c: sqlite3.Connection, submission_id: int) -> list[IssueView]:
        crit = c.execute("SELECT id FROM critiques WHERE submission_id = ? ORDER BY id DESC LIMIT 1",
                         (submission_id,)).fetchone()
        if crit is None:
            return []
        views = []
        for r in c.execute("SELECT * FROM issues WHERE critique_id = ? ORDER BY position", (crit["id"],)):
            rating = c.execute(
                f"SELECT type FROM events WHERE issue_id = ? AND type IN ({','.join('?' * len(RATINGS))}) "
                "ORDER BY id DESC LIMIT 1", (r["id"], *RATINGS)).fetchone()
            intentional = c.execute("SELECT 1 FROM events WHERE issue_id = ? AND type = 'intentional'",
                                    (r["id"],)).fetchone()
            views.append(IssueView(r["id"], r["position"], r["category"], r["title"], r["instruction"],
                                   json.loads(r["drawing_cells"]), json.loads(r["photo_cells"]),
                                   rating["type"] if rating else None, intentional is not None))
        return views

    def get_submission(self, submission_id: int) -> SubmissionView | None:
        with self._conn() as c:
            s = c.execute(
                "SELECT s.*, d.photo_path, d.photo_crop, d.photo_source_url, d.photo_license, d.publish "
                "FROM submissions s JOIN drawings d ON d.id = s.drawing_id WHERE s.id = ?", (submission_id,)
            ).fetchone()
            if s is None:
                return None
            st = c.execute("SELECT status, detail FROM submission_status WHERE submission_id = ? "
                           "ORDER BY id DESC LIMIT 1", (submission_id,)).fetchone()
            crit = c.execute("SELECT model, lessons_sha FROM critiques WHERE submission_id = ? ORDER BY id DESC LIMIT 1",
                             (submission_id,)).fetchone()
            return SubmissionView(
                s["id"], s["drawing_id"], s["version"], s["normalized_path"], s["photo_path"],
                tuple(json.loads(s["photo_crop"])), s["photo_source_url"], s["photo_license"], bool(s["publish"]),
                st["status"], st["detail"], crit["model"] if crit else None, crit["lessons_sha"] if crit else None,
                self._issue_views(c, submission_id), s["parent_id"],
            )

    def add_outcome(self, row: OutcomeRow) -> int:
        return self._insert(
            "INSERT INTO outcomes (issue_id, revision_submission_id, judge_verdict, judge_reason, geometry_json, "
            "final_verdict, source, disagreement) VALUES (?,?,?,?,?,?,?,?)",
            (row.issue_id, row.revision_submission_id, row.judge_verdict, row.judge_reason, row.geometry_json,
             row.final_verdict, row.source, int(row.disagreement)))

    def outcomes_for(self, revision_submission_id: int) -> list[OutcomeView]:
        """Latest outcome row per issue for a revision, in issue order."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT o.*, i.position, i.category, i.title FROM outcomes o JOIN issues i ON i.id = o.issue_id "
                "WHERE o.id IN (SELECT MAX(id) FROM outcomes WHERE revision_submission_id = ? GROUP BY issue_id) "
                "ORDER BY i.position", (revision_submission_id,)).fetchall()
        return [OutcomeView(r["issue_id"], r["position"], r["category"], r["title"], r["final_verdict"], r["source"],
                            r["judge_verdict"], r["judge_reason"], bool(r["disagreement"])) for r in rows]

    def add_revision_metrics(self, submission_id: int, overall_old: float | None, overall_new: float | None) -> int:
        return self._insert("INSERT INTO revision_metrics (submission_id, overall_old, overall_new) VALUES (?,?,?)",
                            (submission_id, overall_old, overall_new))

    def revision_metrics(self, submission_id: int) -> tuple[float | None, float | None] | None:
        with self._conn() as c:
            r = c.execute("SELECT overall_old, overall_new FROM revision_metrics WHERE submission_id = ? "
                          "ORDER BY id DESC LIMIT 1", (submission_id,)).fetchone()
        return (r["overall_old"], r["overall_new"]) if r else None

    def latest_submission(self, drawing_id: int) -> int | None:
        with self._conn() as c:
            row = c.execute("SELECT MAX(id) AS id FROM submissions WHERE drawing_id = ?", (drawing_id,)).fetchone()
        return row["id"]

    # ---- read-only queries for the dreamer ----
    def evidence_issue_rows(self, after_submission: int, after_outcome: int, after_event: int) -> list[sqlite3.Row]:
        """Issues of done submissions that are new, or have outcomes/feedback newer than the given ids."""
        with self._conn() as c:
            return c.execute(
                "SELECT i.id, i.submission_id, i.position, i.category, i.title, i.instruction, i.lesson_refs "
                "FROM issues i JOIN submissions s ON s.id = i.submission_id "
                "WHERE i.critique_id = (SELECT MAX(id) FROM critiques WHERE submission_id = s.id) "
                "AND (SELECT status FROM submission_status WHERE submission_id = s.id ORDER BY id DESC LIMIT 1) = 'done' "
                "AND (s.id > ? OR EXISTS (SELECT 1 FROM outcomes o WHERE o.issue_id = i.id AND o.id > ?) "
                "OR EXISTS (SELECT 1 FROM events e WHERE e.issue_id = i.id AND e.id > ? "
                "AND e.type IN ('thumb_up','thumb_down','unclear','intentional','show_me'))) "
                "ORDER BY i.submission_id, i.position", (after_submission, after_outcome, after_event)).fetchall()

    def issue_outcomes(self, issue_id: int) -> list[sqlite3.Row]:
        """Latest outcome per revision for one issue."""
        with self._conn() as c:
            return c.execute(
                "SELECT final_verdict, source, disagreement FROM outcomes WHERE id IN "
                "(SELECT MAX(id) FROM outcomes WHERE issue_id = ? GROUP BY revision_submission_id) ORDER BY id",
                (issue_id,)).fetchall()

    def is_intentional(self, issue_id: int) -> bool:
        with self._conn() as c:
            return c.execute("SELECT 1 FROM events WHERE issue_id = ? AND type = 'intentional'",
                             (issue_id,)).fetchone() is not None

    def max_ids(self) -> tuple[int, int, int]:
        """(latest done submission id, latest outcome id, latest event id)."""
        with self._conn() as c:
            sub = c.execute(
                "SELECT MAX(s.id) AS m FROM submissions s WHERE (SELECT status FROM submission_status "
                "WHERE submission_id = s.id ORDER BY id DESC LIMIT 1) = 'done'").fetchone()["m"]
            out = c.execute("SELECT MAX(id) AS m FROM outcomes").fetchone()["m"]
            ev = c.execute("SELECT MAX(id) AS m FROM events").fetchone()["m"]
        return sub or 0, out or 0, ev or 0

    def user_texts(self) -> list[str]:
        """Everything a user typed that is stored: photo licenses and source links."""
        with self._conn() as c:
            rows = c.execute("SELECT photo_license, photo_source_url FROM drawings").fetchall()
        return sorted({t for r in rows for t in (r["photo_license"], r["photo_source_url"]) if t})

    def effective_publish(self, drawing_id: int) -> bool:
        """Latest publish_toggle event for the drawing wins; otherwise the flag chosen at upload."""
        with self._conn() as c:
            ev = c.execute("SELECT payload FROM events WHERE type = 'publish_toggle' "
                           "AND json_extract(payload, '$.drawing_id') = ? ORDER BY id DESC LIMIT 1",
                           (drawing_id,)).fetchone()
            if ev is not None:
                return bool(json.loads(ev["payload"]).get("publish"))
            row = c.execute("SELECT publish FROM drawings WHERE id = ?", (drawing_id,)).fetchone()
        return bool(row and row["publish"])

    def published_drawing_ids(self) -> list[int]:
        with self._conn() as c:
            ids = [r["id"] for r in c.execute("SELECT id FROM drawings ORDER BY id")]
        return [d for d in ids if self.effective_publish(d)]

    def rating_counts(self, issue_id: int) -> dict[str, int]:
        keys = ("thumb_up", "thumb_down", "unclear", "show_me")
        with self._conn() as c:
            rows = c.execute(f"SELECT type, COUNT(*) AS n FROM events WHERE issue_id = ? AND type IN "
                             f"({','.join('?' * len(keys))}) GROUP BY type", (issue_id, *keys)).fetchall()
        counts = {r["type"]: r["n"] for r in rows}
        return {k: counts.get(k, 0) for k in keys}

    def latest_done_submission(self, drawing_id: int) -> int | None:
        """Newest version whose latest status is 'done' — the one a revision should be checked against."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT s.id, st.status FROM submissions s JOIN submission_status st ON st.submission_id = s.id "
                "WHERE s.drawing_id = ? AND st.id IN (SELECT MAX(id) FROM submission_status GROUP BY submission_id) "
                "ORDER BY s.id DESC", (drawing_id,)).fetchall()
        return next((r["id"] for r in rows if r["status"] == "done"), None)

    def versions(self, drawing_id: int) -> list[tuple[int, int]]:
        with self._conn() as c:
            rows = c.execute("SELECT id, version FROM submissions WHERE drawing_id = ? ORDER BY version",
                             (drawing_id,)).fetchall()
        return [(r["id"], r["version"]) for r in rows]

    def unfinished_submissions(self) -> list[int]:
        """Submissions whose latest status is queued or running."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT submission_id, status FROM submission_status WHERE id IN "
                "(SELECT MAX(id) FROM submission_status GROUP BY submission_id)").fetchall()
        return [r["submission_id"] for r in rows if r["status"] in ("queued", "running")]

    def intentional_boxes(self, drawing_id: int) -> list[Box]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT DISTINCT i.id, i.drawing_cells FROM events e JOIN issues i ON i.id = e.issue_id "
                "JOIN submissions s ON s.id = i.submission_id WHERE e.type = 'intentional' AND s.drawing_id = ? "
                "ORDER BY i.id", (drawing_id,)).fetchall()
        return [cells_to_box(json.loads(r["drawing_cells"])) for r in rows]
