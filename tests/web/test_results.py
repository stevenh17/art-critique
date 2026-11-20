import re

import pytest

from .conftest import answer, submit, upload


@pytest.fixture
def done(make_client):
    client, _, app = make_client([answer()])
    url = submit(client, upload(client).headers["location"]).headers["location"]
    view = app.state.store.get_submission(int(url.rsplit("/", 1)[1]))
    return client, url, view, app


def test_results_show_both_images(done):
    client, url, view, _ = done
    page = client.get(url).text
    assert f'src="/images/{view.normalized_path}"' in page
    assert "/photo-crop" in page  # cropped reference


def test_numbered_boxes_on_both_images_match_issue_boxes(done):
    client, url, view, _ = done
    page = client.get(url).text
    for side in ("drawing", "photo"):
        boxes = re.findall(rf'class="box box-{side}"[^>]*data-n="(\d)"[^>]*style="left:([\d.]+)%;top:([\d.]+)%;width:([\d.]+)%;height:([\d.]+)%', page)
        assert [b[0] for b in boxes] == ["1", "2"]
        x0, y0, x1, y1 = getattr(view.issues[0], f"{side}_box")
        assert [float(v) for v in boxes[0][1:]] == pytest.approx([x0 * 100, y0 * 100, (x1 - x0) * 100, (y1 - y0) * 100])


def test_issue_cards_show_title_and_instruction(done):
    client, url, _, _ = done
    page = client.get(url).text
    assert "Jaw too long" in page and "Shorten the chin by about a quarter head." in page


def test_thumb_up_records_event_and_marks_active(done):
    client, _, view, app = done
    iid = view.issues[0].id
    r = client.post(f"/issues/{iid}/events", data={"type": "thumb_up"})
    assert r.status_code == 200 and 'data-active="thumb_up"' in r.text
    assert app.state.store.get_submission(view.id).issues[0].rating == "thumb_up"


def test_intentional_collapses_and_is_remembered(done):
    client, _, view, app = done
    iid = view.issues[0].id
    r = client.post(f"/issues/{iid}/events", data={"type": "intentional"})
    assert "marked as intentional" in r.text.lower()
    assert app.state.store.intentional_boxes(view.drawing_id) == [view.issues[0].drawing_box]


def test_show_me_returns_two_zoomed_crops(done):
    client, _, view, _ = done
    r = client.post(f"/issues/{view.issues[0].id}/events", data={"type": "show_me"})
    srcs = re.findall(r'src="(/images/zoom/[^"]+)"', r.text)
    assert len(srcs) == 2
    assert all(client.get(s).status_code == 200 for s in srcs)


def test_invalid_event_type_is_422(done):
    client, _, view, _ = done
    assert client.post(f"/issues/{view.issues[0].id}/events", data={"type": "love_it"}).status_code == 422


def test_unknown_issue_is_404(done):
    client, _, _, _ = done
    assert client.post("/issues/9999/events", data={"type": "thumb_up"}).status_code == 404


def test_overlay_toggle_and_slider_present(done):
    client, url, _, _ = done
    page = client.get(url).text
    assert 'id="overlay-toggle"' in page and 'type="range"' in page


def test_hidden_attribute_wins_over_display_rules(done):
    client, _, _, _ = done
    css = client.get("/static/app.css").text
    assert re.search(r"\[hidden\]\s*\{\s*display:\s*none\s*!important", css)
