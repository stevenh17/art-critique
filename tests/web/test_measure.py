import json

from .test_revision_results import FakeGeometry, judge, revise
from .conftest import answer

SIX = [[0.3, 0.4], [0.7, 0.4], [0.5, 0.55], [0.5, 0.9], [0.5, 0.15], [0.5, 0.72]]


def judged_revision(make_client):
    # geometry unavailable → proportion issue 1 stays "judged"
    class NoGeo(FakeGeometry):
        def compare(self, d, p):
            from .test_revision_results import Comp

            return Comp(False, None, None)

    client, _, app = make_client([answer(), judge("not_fixed"), judge("partly"), answer()], geometry=NoGeo())
    url = revise(client, app)
    view = app.state.store.get_submission(int(url.rsplit("/", 1)[1]))
    issue1 = app.state.store.outcomes_for(view.id)[0].issue_id
    return client, url, view, issue1, app


def test_measure_link_only_on_judged_proportion(make_client):
    client, url, view, issue1, _ = judged_revision(make_client)
    page = client.get(url).text
    assert f'href="{url}/measure?issue={issue1}"' in page
    assert page.count("Help me measure") == 1  # issue 2 is "values"


def test_measure_page_has_three_images(make_client):
    client, url, _, issue1, _ = judged_revision(make_client)
    page = client.get(f"{url}/measure?issue={issue1}").text
    assert page.count('class="measure-img"') == 3 and "chin" in page


def test_measure_post_appends_outcome_and_overrides(make_client):
    client, url, view, issue1, app = judged_revision(make_client)
    old = [p[:] for p in SIX]
    old[3] = [0.45, 0.8]  # chin misplaced before (inside the issue box C7–D7)
    r = client.post(f"{url}/measure", data={"issue_id": issue1, "points": json.dumps({"photo": SIX, "old": old, "new": SIX})},
                    follow_redirects=False)
    assert r.status_code == 303
    o = app.state.store.outcomes_for(view.id)[0]
    assert o.source == "geometry:points" and o.final_verdict == "fixed"
    assert "measured" in client.get(url).text


def test_measure_rejects_wrong_point_count_422(make_client):
    client, url, _, issue1, _ = judged_revision(make_client)
    bad = json.dumps({"photo": SIX[:5], "old": SIX, "new": SIX})
    assert client.post(f"{url}/measure", data={"issue_id": issue1, "points": bad}).status_code == 422


def test_measure_rejects_out_of_range_422(make_client):
    client, url, _, issue1, _ = judged_revision(make_client)
    bad = json.dumps({"photo": SIX, "old": SIX, "new": [[1.5, 0.2]] + SIX[1:]})
    assert client.post(f"{url}/measure", data={"issue_id": issue1, "points": bad}).status_code == 422
