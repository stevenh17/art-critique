import json

from .conftest import answer, png_bytes, submit, upload

CORNERS = json.dumps([[60, 40], [340, 40], [340, 260], [60, 260]])


def first_version(client):
    url = submit(client, upload(client).headers["location"]).headers["location"]
    return int(url.rsplit("/", 1)[1])


def upload_revision(client, drawing_id):
    return client.post(f"/drawings/{drawing_id}/revisions", files={"drawing": ("r.png", png_bytes(), "image/png")},
                       follow_redirects=False)


def test_revise_form_404_for_unknown_drawing(make_client):
    client, _, _ = make_client([])
    assert client.get("/drawings/999/revise").status_code == 404


def test_revise_form_has_single_file_input(make_client):
    client, _, app = make_client([answer()])
    d = app.state.store.get_submission(first_version(client)).drawing_id
    html = client.get(f"/drawings/{d}/revise").text
    assert 'name="drawing"' in html and 'name="photo"' not in html


def test_revision_adjust_page_has_no_photo_crop(make_client):
    client, _, app = make_client([answer()])
    d = app.state.store.get_submission(first_version(client)).drawing_id
    page = client.get(upload_revision(client, d).headers["location"]).text
    assert 'name="corners"' in page and "crop-stage" not in page


def test_revision_flow_creates_version_2_with_parent(make_client):
    client, _, app = make_client([answer(), answer()])
    s1 = first_version(client)
    v1 = app.state.store.get_submission(s1)
    adjust = upload_revision(client, v1.drawing_id).headers["location"]
    r = client.post(adjust.rsplit("/adjust", 1)[0] + "/submit", data={"corners": CORNERS}, follow_redirects=False)
    assert r.status_code == 303
    v2 = app.state.store.get_submission(int(r.headers["location"].rsplit("/", 1)[1]))
    assert (v2.drawing_id, v2.version, v2.parent_id) == (v1.drawing_id, 2, s1)


def test_revision_reuses_photo_and_crop(make_client):
    client, _, app = make_client([answer(), answer()])
    v1 = app.state.store.get_submission(first_version(client))
    adjust = upload_revision(client, v1.drawing_id).headers["location"]
    r = client.post(adjust.rsplit("/adjust", 1)[0] + "/submit", data={"corners": CORNERS}, follow_redirects=False)
    v2 = app.state.store.get_submission(int(r.headers["location"].rsplit("/", 1)[1]))
    assert (v2.photo_path, v2.photo_crop, v2.photo_license) == (v1.photo_path, v1.photo_crop, v1.photo_license)


def test_done_page_links_to_revise_and_versions(make_client):
    client, _, app = make_client([answer()])
    s1 = first_version(client)
    d = app.state.store.get_submission(s1).drawing_id
    page = client.get(f"/submissions/{s1}").text
    assert f'href="/drawings/{d}/revise"' in page
    assert f'href="/submissions/{s1}"' in page and "v1" in page


def test_revision_parent_is_last_done_version(make_client):
    client, _, app = make_client([answer(), answer("bad"), answer("bad"), answer()])
    s1 = first_version(client)
    d = app.state.store.get_submission(s1).drawing_id
    adjust = upload_revision(client, d).headers["location"]
    s2 = int(client.post(adjust.rsplit("/adjust", 1)[0] + "/submit", data={"corners": CORNERS},
                         follow_redirects=False).headers["location"].rsplit("/", 1)[1])
    assert app.state.store.get_submission(s2).status == "failed"
    adjust = upload_revision(client, d).headers["location"]
    s3 = int(client.post(adjust.rsplit("/adjust", 1)[0] + "/submit", data={"corners": CORNERS},
                         follow_redirects=False).headers["location"].rsplit("/", 1)[1])
    v3 = app.state.store.get_submission(s3)
    assert v3.parent_id == s1 and v3.version == 3
