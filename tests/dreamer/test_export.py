import dataclasses
import json

from artcrit.dreamer.export import Watermark, export_since, has_enough_evidence
from tests.site.conftest import outcome


def test_watermark_roundtrip_and_tolerant_load():
    wm = Watermark(3, 4, 5)
    assert Watermark.load(wm.dumps()) == wm
    assert Watermark.load(None) == Watermark() == Watermark.load("not json") == Watermark.load('{"x": 1}')


def test_new_submissions_exported(world):
    d, (s1,) = world.drawing()
    ex = export_since(world.store, Watermark())
    assert [(r.session, r.issue_number, r.category) for r in ex.records] == [(f"s{s1}", 1, "proportion"), (f"s{s1}", 2, "values")]
    assert ex.new_watermark.submission == s1


def test_old_issue_with_new_outcome_exported(world):
    d, (s1, s2) = world.drawing(versions=2)
    wm = export_since(world.store, Watermark()).new_watermark
    assert export_since(world.store, wm).records == []
    iid = world.store.get_submission(s1).issues[0].id
    outcome(world.store, iid, s2, "fixed", "geometry:outline")
    recs = export_since(world.store, wm).records
    assert [(r.session, r.issue_number) for r in recs] == [(f"s{s1}", 1)]
    assert recs[0].outcomes == [{"verdict": "fixed", "measured": True, "disagreement": True}]


def test_old_issue_with_new_rating_exported(world):
    d, (s1,) = world.drawing()
    wm = export_since(world.store, Watermark()).new_watermark
    iid = world.store.get_submission(s1).issues[1].id
    world.store.add_event("thumb_up", issue_id=iid)
    world.store.add_event("thumb_up", issue_id=iid)
    recs = export_since(world.store, wm).records
    assert len(recs) == 1 and recs[0].ratings["thumb_up"] == 2 and recs[0].issue_number == 2


def test_intentional_flag_and_new_event_watermark(world):
    d, (s1,) = world.drawing()
    wm = export_since(world.store, Watermark()).new_watermark
    iid = world.store.get_submission(s1).issues[0].id
    eid = world.store.add_event("intentional", issue_id=iid)
    ex = export_since(world.store, wm)
    assert ex.records[0].intentional and ex.new_watermark.event == eid


def test_nothing_new_gives_empty_export(world):
    world.drawing()
    wm = export_since(world.store, Watermark()).new_watermark
    ex = export_since(world.store, wm)
    assert ex.records == [] and ex.new_watermark == wm


def test_failed_submissions_excluded(world):
    world.drawing(done=False)
    assert export_since(world.store, Watermark()).records == []


def test_records_have_no_paths_or_traces(world):
    d, (s1, s2) = world.drawing(versions=2)
    outcome(world.store, world.store.get_submission(s1).issues[0].id, s2)
    blob = json.dumps([dataclasses.asdict(r) for r in export_since(world.store, Watermark()).records])
    for word in ("data/", "tool_trace", "judge_reason", "private reason", ".png", "zoom"):
        assert word not in blob


def test_user_texts_collected(world):
    world.drawing(url="https://example.org/photo", license="CC BY 4.0 — Jane Doe")
    assert set(export_since(world.store, Watermark()).user_texts) >= {"https://example.org/photo", "CC BY 4.0 — Jane Doe"}


def test_has_enough_evidence_threshold(world):
    d, (s1, s2) = world.drawing(versions=2)
    ex = export_since(world.store, Watermark())
    assert not has_enough_evidence(ex)  # issues but no outcomes or ratings
    issues = world.store.get_submission(s1).issues
    outcome(world.store, issues[0].id, s2)
    outcome(world.store, issues[1].id, s2)
    world.store.add_event("thumb_down", issue_id=world.store.get_submission(s2).issues[0].id)
    assert has_enough_evidence(export_since(world.store, Watermark()))
