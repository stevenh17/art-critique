import dataclasses
import json

from artcrit.site.model import build_site_data

from .conftest import outcome


def ids(data):
    return [d.id for d in data.drawings]


def test_unpublished_drawing_excluded(world):
    a, _ = world.drawing(publish=True)
    world.drawing(publish=False)
    assert ids(build_site_data(world.store, world.tmp)) == [a]


def test_toggle_event_overrides_flag(world):
    a, _ = world.drawing(publish=True)
    world.store.add_event("publish_toggle", payload={"publish": False}, submission_id=None)
    world.store.add_event("publish_toggle", payload={"publish": False, "drawing_id": a})
    assert world.store.effective_publish(a) is False
    assert ids(build_site_data(world.store, world.tmp)) == []
    world.store.add_event("publish_toggle", payload={"publish": True, "drawing_id": a})
    assert ids(build_site_data(world.store, world.tmp)) == [a]


def test_only_done_versions_included(world):
    d, (s1, s2) = world.drawing(versions=2)
    world.store.add_status(s2, "failed", "boom")
    data = build_site_data(world.store, world.tmp)
    assert [v.version for v in data.drawings[0].versions] == [1]


def test_drawing_with_no_done_versions_excluded(world):
    world.drawing(done=False)
    assert ids(build_site_data(world.store, world.tmp)) == []


def test_issues_and_outcomes_carried(world):
    d, (s1, s2) = world.drawing(versions=2)
    issue_ids = [i.id for i in world.store.get_submission(s1).issues]
    outcome(world.store, issue_ids[0], s2, "fixed", "geometry:outline")
    outcome(world.store, issue_ids[1], s2, "not_fixed", "judge")
    world.store.add_revision_metrics(s2, 0.10, 0.08)
    v1, v2 = build_site_data(world.store, world.tmp).drawings[0].versions
    assert [(i.number, i.title, i.drawing_box) for i in v1.issues][0] == (1, "Jaw too long", (0.25, 0.75, 0.375, 0.875))
    assert [(o.number, o.verdict, o.measured) for o in v2.outcomes] == [(1, "fixed", True), (2, "not_fixed", False)]
    assert abs(v2.closeness - 0.2) < 1e-9 and v1.closeness is None
    assert (v1.slug, v1.lessons_sha, v1.model) == (f"d{d}-v1", "sha123", "claude-x")


def test_ratings_are_counts_only(world):
    _, (s1,) = world.drawing()
    iid = world.store.get_submission(s1).issues[0].id
    for t in ("thumb_up", "thumb_up", "thumb_down"):
        world.store.add_event(t, issue_id=iid)
    issue = build_site_data(world.store, world.tmp).drawings[0].versions[0].issues[0]
    assert issue.ratings == {"thumb_up": 2, "thumb_down": 1, "unclear": 0, "show_me": 0}


def test_no_private_fields(world):
    d, (s1, s2) = world.drawing(versions=2)
    outcome(world.store, world.store.get_submission(s1).issues[0].id, s2)
    blob = json.dumps(dataclasses.asdict(build_site_data(world.store, world.tmp)))
    for word in ("tool_trace", "status_detail", "judge_reason", "private reason", "original", "zoom"):
        assert word not in blob


def test_non_http_source_url_dropped(world):
    world.drawing(url="javascript:alert(1)")
    assert build_site_data(world.store, world.tmp).drawings[0].source_url is None


def test_title_and_slug(world):
    d, _ = world.drawing()
    dr = build_site_data(world.store, world.tmp).drawings[0]
    assert (dr.title, dr.slug) == (f"Drawing {d}", f"d{d}")
