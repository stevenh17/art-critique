from artcrit.engine.base import UsageLimitError

from .conftest import answer, submit, upload


def _limit(tools):
    raise UsageLimitError("five_hour")


def _flow(client):
    return submit(client, upload(client).headers["location"]).headers["location"]


def test_usage_limit_sets_limit_status_with_retry(make_client):
    client, _, _ = make_client([_limit])
    page = client.get(_flow(client)).text
    assert "usage limit reached" in page.lower()
    assert "Retry" in page


def test_two_bad_outputs_set_failed(make_client):
    client, _, _ = make_client([answer("bad"), answer("worse")])
    page = client.get(_flow(client)).text
    assert "critique failed — retry" in page


def test_retry_after_limit_succeeds(make_client):
    client, _, _ = make_client([_limit, answer()])
    url = _flow(client)
    r = client.post(f"{url}/retry", follow_redirects=False)
    assert r.status_code == 303
    assert "Jaw too long" in client.get(url).text


def test_retry_on_done_is_409(make_client):
    client, _, _ = make_client([answer()])
    url = _flow(client)
    assert client.post(f"{url}/retry").status_code == 409


def test_status_fragment_reports_state(make_client):
    client, _, _ = make_client([answer()])
    url = _flow(client)
    r = client.get(f"{url}/status")
    assert r.status_code == 200 and r.headers.get("HX-Refresh") == "true"
