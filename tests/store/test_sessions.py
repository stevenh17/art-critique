import re
from pathlib import Path

import pytest

from artcrit.critic import CritiqueRun
from artcrit.critique_schema import parse_critique
from artcrit.store.sessions import SessionStore

CRIT = parse_critique('{"issues": ['
    '{"category": "proportion", "title": "Jaw too long", "instruction": "Shorten it.", "drawing_cells": ["C7","D7"], "photo_cells": ["C6"]},'
    '{"category": "values", "title": "Shadow light", "instruction": "Darken.", "drawing_cells": ["B3"], "photo_cells": ["B3"]}]}')
RUN = CritiqueRun(CRIT, [{"tool": "zoom", "input": {}}], "claude-test", "abc123")


@pytest.fixture
def store(tmp_path):
    return SessionStore(tmp_path / "s.db")


def _submission(store):
    d = store.add_drawing("photo/p.png", (0.1, 0.1, 0.9, 0.9), "https://unsplash.com/x", "Unsplash", True)
    s = store.add_submission(d, 1, None, "orig/o.png", "drawing/n.png", ((0, 0), (9, 0), (9, 9), (0, 9)))
    return d, s


def test_roundtrip_shows_issues(store):
    d, s = _submission(store)
    ids = store.add_critique(s, RUN)
    view = store.get_submission(s)
    assert view.drawing_id == d and view.version == 1
    assert [i.id for i in view.issues] == ids
    assert view.issues[0].title == "Jaw too long"
    assert view.issues[0].drawing_box == (0.25, 0.75, 0.5, 0.875)
    assert view.model == "claude-test" and view.lessons_sha == "abc123"
    assert view.photo_license == "Unsplash"


def test_new_submission_is_queued(store):
    _, s = _submission(store)
    assert store.get_submission(s).status == "queued"


def test_latest_status_wins(store):
    _, s = _submission(store)
    store.add_status(s, "running")
    store.add_status(s, "done")
    assert store.get_submission(s).status == "done"


def test_status_detail_kept(store):
    _, s = _submission(store)
    store.add_status(s, "limit", "five_hour")
    v = store.get_submission(s)
    assert (v.status, v.status_detail) == ("limit", "five_hour")


def test_invalid_status_rejected(store):
    _, s = _submission(store)
    with pytest.raises(ValueError):
        store.add_status(s, "finished")


def test_intentional_event_feeds_intentional_boxes(store):
    d, s = _submission(store)
    ids = store.add_critique(s, RUN)
    store.add_event("intentional", issue_id=ids[0])
    assert store.intentional_boxes(d) == [(0.25, 0.75, 0.5, 0.875)]
    assert store.get_submission(s).issues[0].intentional is True


def test_latest_rating_shown(store):
    _, s = _submission(store)
    ids = store.add_critique(s, RUN)
    store.add_event("thumb_up", issue_id=ids[1])
    store.add_event("thumb_down", issue_id=ids[1])
    assert store.get_submission(s).issues[1].rating == "thumb_down"


def test_unknown_event_type_raises(store):
    with pytest.raises(ValueError):
        store.add_event("love_it", issue_id=1)


def test_missing_submission_returns_none(store):
    assert store.get_submission(999) is None


def test_no_update_or_delete_sql():
    root = Path(__file__).resolve().parents[2] / "artcrit" / "store"
    text = "\n".join(p.read_text() for p in root.rglob("*") if p.suffix in {".py", ".sql"})
    assert not re.search(r"\b(UPDATE|DELETE)\s", text, re.IGNORECASE)


def test_latest_submission_and_versions(store):
    d, s1 = _submission(store)
    s2 = store.add_submission(d, 2, s1, "orig/o2.png", "drawing/n2.png", ((0, 0), (9, 0), (9, 9), (0, 9)))
    assert store.latest_submission(d) == s2
    assert store.versions(d) == [(s1, 1), (s2, 2)]
    assert store.get_submission(s2).parent_id == s1
    assert store.latest_submission(999) is None
