from artcrit.cli import build_parser

from .conftest import answer, png_bytes, submit, upload


def test_upload_form_has_required_fields(make_client):
    client, _, _ = make_client([])
    html = client.get("/").text
    for name in ('name="drawing"', 'name="photo"', 'name="photo_source_url"', 'name="photo_license"', 'name="publish"'):
        assert name in html
    assert "checked" in html  # publish defaults on


def test_upload_redirects_to_adjust_with_detected_corners(make_client):
    client, _, _ = make_client([])
    r = upload(client)
    assert r.status_code == 303 and r.headers["location"].endswith("/adjust")
    page = client.get(r.headers["location"]).text
    assert 'name="corners"' in page and 'name="photo_crop"' in page
    import html
    import json
    import re

    corners = json.loads(html.unescape(re.search(r'name="corners" id="corners" value="([^"]+)"', page).group(1)))
    assert abs(corners[0][0] - 60) <= 3 and abs(corners[0][1] - 40) <= 3  # paper, not the full image


def test_upload_without_paper_falls_back_to_full_image(make_client):
    client, _, _ = make_client([])
    r = upload(client, drawing=png_bytes(paper=False))
    page = client.get(r.headers["location"]).text
    assert "[[0.0, 0.0]" in page.replace("&#34;", '"')


def test_missing_license_is_422(make_client):
    client, _, _ = make_client([])
    assert upload(client, license="").status_code == 422


def test_unreadable_image_is_422(make_client):
    client, _, _ = make_client([])
    r = client.post("/uploads", files={"drawing": ("d.png", b"junk", "image/png"), "photo": ("p.png", png_bytes(), "image/png")},
                    data={"photo_source_url": "https://example.org/p", "photo_license": "CC0"}, follow_redirects=False)
    assert r.status_code == 422 and "image" in r.text.lower()


def test_full_flow_shows_done_with_two_issues(make_client):
    client, engine, _ = make_client([answer()])
    r = submit(client, upload(client).headers["location"])
    assert r.status_code == 303 and r.headers["location"].startswith("/submissions/")
    page = client.get(r.headers["location"]).text
    assert "Jaw too long" in page and "Shadow too light" in page
    assert len(engine.calls) == 1


def test_unknown_upload_token_is_404(make_client):
    client, _, _ = make_client([])
    assert client.get("/uploads/doesnotexist/adjust").status_code == 404


def test_serve_binds_localhost():
    args = build_parser().parse_args(["serve"])
    assert args.host == "127.0.0.1" and args.port == 8000


def test_adjust_page_images_are_served(make_client):
    client, _, _ = make_client([])
    page = client.get(upload(client).headers["location"]).text
    import re

    src = re.search(r'src="(/images/original/[^"]+)"', page).group(1)
    r = client.get(src)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_image_route_blocks_traversal(make_client):
    client, _, _ = make_client([])
    assert client.get("/images/../../pyproject.toml").status_code == 404
    assert client.get("/images/%2e%2e/%2e%2e/pyproject.toml").status_code == 404


def test_non_http_source_url_is_422(make_client):
    client, _, _ = make_client([])
    r = client.post("/uploads", files={"drawing": ("d.png", png_bytes(), "image/png"), "photo": ("p.png", png_bytes(), "image/png")},
                    data={"photo_source_url": "javascript:alert(1)", "photo_license": "CC0"}, follow_redirects=False)
    assert r.status_code == 422


def test_degenerate_corners_are_422_not_500(make_client):
    import json

    client, _, _ = make_client([])
    base = upload(client).headers["location"].rsplit("/adjust", 1)[0]
    r = client.post(f"{base}/submit", data={"corners": json.dumps([[5, 5]] * 4), "photo_crop": "[0,0,1,1]"})
    assert r.status_code == 422
