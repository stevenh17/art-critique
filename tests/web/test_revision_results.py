import json
from dataclasses import dataclass

from artcrit.engine.base import AgentResult, UsageLimitError

from .conftest import answer, submit, upload
from .test_revision_upload import CORNERS, first_version, upload_revision


def judge(v):
    return lambda tools: AgentResult(json.dumps({"verdict": v, "reason": "because"}), [], "m")


@dataclass
class Comp:
    available: bool
    region: float | None
    overall: float | None
    sim: object = None  # no alignment: map_box keeps the box as-is

    def region_distance(self, box):
        return self.region


@dataclass
class NoFace:
    available: bool = False


class FakeGeometry:
    """First compare() is the old version, second the new one."""

    def __init__(self, old=0.10, new=0.03):
        self.vals = [old, new]
        self.calls = 0

    def compare(self, drawing, photo):
        v = self.vals[min(self.calls, 1)]
        self.calls += 1
        return Comp(True, v, v)

    def faces(self, drawing, photo):
        return NoFace()


def revise(client, app):
    s1 = first_version(client)
    d = app.state.store.get_submission(s1).drawing_id
    adjust = upload_revision(client, d).headers["location"]
    r = client.post(adjust.rsplit("/adjust", 1)[0] + "/submit", data={"corners": CORNERS}, follow_redirects=False)
    return r.headers["location"]


def test_revision_page_shows_outcomes_and_new_critique(make_client):
    client, eng, app = make_client([answer(), judge("partly"), judge("not_fixed"), answer()])
    page = client.get(revise(client, app)).text
    assert "Since v1" in page
    assert "Jaw too long" in page and "partly" in page and "not fixed" in page
    assert page.index("Since v1") < page.index('class="issues"')
    assert len(eng.calls) == 4


def test_outcome_chip_text_measured_vs_judged(make_client):
    client, _, app = make_client([answer(), judge("not_fixed"), judge("not_fixed"), answer()], geometry=FakeGeometry())
    page = client.get(revise(client, app)).text
    # issue 1 is proportion: confident geometry (0.10 → 0.03) overrides the judge
    assert 'data-verdict="fixed"' in page and "measured" in page
    assert "judged" in page  # issue 2 (values) stays with the judge


def test_closeness_line_shown(make_client):
    client, _, app = make_client([answer(), judge("fixed"), judge("fixed"), answer()], geometry=FakeGeometry(0.10, 0.08))
    page = client.get(revise(client, app)).text
    assert "20% closer to the reference" in page


def test_nothing_to_compare_when_parent_failed(make_client):
    client, eng, app = make_client([answer("bad"), answer("bad"), answer()])
    page = client.get(revise(client, app)).text
    assert "Nothing to compare yet" in page and "Jaw too long" in page  # fresh critique still ran
    assert len(eng.calls) == 3


def test_usage_limit_during_judging_then_retry_no_duplicates(make_client):
    def limit(tools):
        raise UsageLimitError("five_hour")

    client, _, app = make_client([answer(), limit, judge("fixed"), judge("partly"), answer()])
    url = revise(client, app)
    assert "usage limit reached" in client.get(url).text.lower()
    client.post(f"{url}/retry")
    page = client.get(url).text
    assert page.count('class="outcome"') == 2


def test_first_version_page_unchanged(make_client):
    client, _, _ = make_client([answer()])
    url = submit(client, upload(client).headers["location"]).headers["location"]
    assert "Since v" not in client.get(url).text


def test_closeness_line_when_worse(make_client):
    client, _, app = make_client([answer(), judge("fixed"), judge("fixed"), answer()], geometry=FakeGeometry(0.10, 0.12))
    page = client.get(revise(client, app)).text
    assert "20% further from the reference" in page and "-20%" not in page
