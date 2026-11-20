from .conftest import answer, submit, upload
from .test_publish_triggers import SpyPublisher, client_with


def setup(tmp_path):
    pub = SpyPublisher()
    client = client_with(tmp_path, [answer()], pub, state='{"lessons_sha": "uncommitted"}')
    url = submit(client, upload(client).headers["location"]).headers["location"]
    store = client.app.state.store
    return client, pub, url, store, store.get_submission(int(url.rsplit("/", 1)[1])).drawing_id


def test_toggle_records_event_and_flips_effective_flag(tmp_path):
    client, _, url, store, d = setup(tmp_path)
    assert store.effective_publish(d) is True
    r = client.post(f"/drawings/{d}/publish", data={"publish": "off"}, follow_redirects=False)
    assert r.status_code == 303 and store.effective_publish(d) is False
    client.post(f"/drawings/{d}/publish", data={"publish": "on"})
    assert store.effective_publish(d) is True


def test_toggle_requests_publish(tmp_path):
    client, pub, _, _, d = setup(tmp_path)
    before = pub.requests
    client.post(f"/drawings/{d}/publish", data={"publish": "off"})
    assert pub.requests == before + 1


def test_toggle_unknown_drawing_404(tmp_path):
    client, *_ = setup(tmp_path)
    assert client.post("/drawings/999/publish", data={"publish": "off"}).status_code == 404


def test_toggle_rejects_bad_value(tmp_path):
    client, _, _, _, d = setup(tmp_path)
    assert client.post(f"/drawings/{d}/publish", data={"publish": "maybe"}).status_code == 422


def test_page_shows_publish_state(tmp_path):
    client, _, url, _, d = setup(tmp_path)
    assert "Published on portfolio" in client.get(url).text
    client.post(f"/drawings/{d}/publish", data={"publish": "off"})
    assert "Not published" in client.get(url).text
